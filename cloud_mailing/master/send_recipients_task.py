# Copyright 2015 Cedric RICARD
#
# This file is part of mf.
#
# mf is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# mf is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with mf.  If not, see <http://www.gnu.org/licenses/>.
import cPickle as pickle
import logging
import re
import time
from datetime import datetime

import pymongo
from bson import DBRef
from twisted.internet import defer
from twisted.spread import util

from cloud_mailing.common.db_common import get_db
from cloud_mailing.common.singletonmixin import Singleton
from cloud_mailing.master import settings_vars
from cloud_mailing.master.models import MAILING_STATUS

__author__ = 'Cedric RICARD'


class SendRecipientsTask(Singleton):
    def __init__(self):
        self.log = logging.getLogger("send_rcpts")

    @staticmethod
    @defer.inlineCallbacks
    def _make_get_recipients_queryset(db, satellite_group, domain_affinity, log):
        """Return a pymongo cursor"""
        included = []
        excluded = []
        try:
            affinity = domain_affinity and eval(domain_affinity)
            if affinity:
                if not isinstance(affinity, dict):
                    raise TypeError, "Affinity is not a dictionary!"
                domain_re = re.compile('^(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?$', re.IGNORECASE)
                #                print self.cloud_client.serial, repr(affinity)
                if affinity.get('enabled', True):
                    for domain, value in affinity.items():
                        if domain == 'enabled':
                            continue
                        if not domain_re.match(domain):
                            log.warning("Wrong domain name format for '%s'. Ignored...", domain)
                            continue
                        if value:
                            # print self.cloud_client.serial, "include", domain
                            included.append(domain)
                        else:
                            # print self.cloud_client.serial, "exclude", domain
                            excluded.append(domain)
        except Exception:
            log.exception("Error in Affinity format")
        mailing_filter = {
            'status': {'$in': [MAILING_STATUS.FILLING_RECIPIENTS,  # For Test recipients
                               MAILING_STATUS.READY,  # For Test recipients
                               MAILING_STATUS.RUNNING]},
            'satellite_group': satellite_group
        }
        _list_of_mailings = yield db.mailing.find(mailing_filter, fields=[])
        mailing_ids = map(lambda x: x['_id'], _list_of_mailings)
        query = {
            '$and': [{'$or': [{'in_progress': False}, {'in_progress': {'$exists': False}}]},
                     {'$or': [{'client': False}, {'client': {'$exists': False}}]},
                     ],
            'mailing.$id': {'$in': mailing_ids},
        }
        if included and excluded:
            query['$and'].extend([
                {'domain_name': {'$in': included}},
                {'domain_name': {'$nin': excluded}},
            ])
        elif included:
            query['domain_name'] = {'$in': included}
        elif excluded:
            query['domain_name'] = {'$nin': excluded}
        defer.returnValue(query)

    def _get_avatar(self, serial):
        from .cloud_master import mailing_portal

        if mailing_portal:
            mailing_master = mailing_portal.realm
            return mailing_master.avatars.get(serial)
        else:
            self.log.error("Can't get MailingPortal object!")

    @defer.inlineCallbacks
    def _send_recipients_to_satellite(self, serial, count):
        self.log.debug("_send_recipients_to_satellite(client=%s, count=%d)", serial, count)
        t0 = time.time()

        avatar = self._get_avatar(serial)
        if not avatar:
            self.log.error("Can't get avatar for '%s'. Client seems to be disconnected.", serial)
            return

        wanted_count, collector = yield avatar.prepare_getting_recipients(count)
        if not wanted_count or not collector:
            self.log.debug("_send_recipients_to_satellite() Client [%s] is already full.", serial)
            return

        db = get_db()

        cloud_client = yield db.cloudclient.find_one({'serial': serial})

        if not cloud_client:
            self.log.warn("_send_recipients_to_satellite() Unknown client [%s]", serial)
            return
        if not cloud_client['enabled']:
            self.log.warn("_send_recipients_to_satellite() refused for disabled client [%s]", serial)
            return
        domain_affinity = cloud_client.get('domain_affinity')
        satellite_group = cloud_client.get('group')
        query_filter = yield self._make_get_recipients_queryset(db, satellite_group,
                                                                domain_affinity, self.log)
        queue = yield db.mailingtempqueue.find(query_filter, sort='next_try', limit=count)
        recipients = []
        ids = []
        for item in queue:
            try:
                rcpt = item['recipient']
                for key in ('cloud_client', 'in_progress', 'read_time'):
                    rcpt.pop(key, None)
                rcpt['sender_name'] = item['sender_name']
                rcpt['mail_from'] = item['mail_from']
                rcpt['mailing'] = item['mailing'].id
                recipients.append(rcpt)
                ids.append(item['_id'])
            except:
                self.log.exception("Error preparing recipient '%s'...", item['email'])

        update_item = {'$set': {
            'client': DBRef('cloudclient', cloud_client['_id']),
            'date_delegated': datetime.utcnow(),
            'in_progress': True,
        }}
        r = yield db.mailingtempqueue.update_many({'_id': {'$in': ids}}, update_item)

        def show_time_at_end(_t0, rcpts_count, data_len):
            self.log.debug("_send_recipients_to_satellite(): Sent %d recipients (%.2f Kb) in %.2f s",
                           rcpts_count, data_len / 1024.0, time.time() - _t0)

        self.log.debug("_send_recipients_to_satellite(): starting sending %d recipients at %.2f s", len(recipients),
                       time.time() - t0)
        data = pickle.dumps(recipients)
        util.StringPager(collector, data, 262144, show_time_at_end, t0, len(recipients), len(data))

    @defer.inlineCallbacks
    def run(self):
        db = get_db()

        # all_satellites = yield db.cloudclient.find({'enabled': True, 'paired': True})
        all_satellites = yield db.cloudclient.find()
        all_satellites_dict = {s['_id']: s for s in all_satellites}
        current_load = yield db.mailingtempqueue.aggregate([
            {
                '$match': {
                    'client': {'$ne': None, '$exists': True}
                }
            },
            {
                '$group': {
                    '_id': '$client',
                    'count': {'$sum': 1}
                }
            },
            {'$sort': {'count': pymongo.DESCENDING}}
        ])
        current_load = {load['_id'].id: load['count'] for load in current_load}
        self.log.debug("Current satellite load:")
        for _id, count in current_load.items():
            self.log.debug("    - %s: %d recipients", all_satellites_dict.get(_id, {}).get('serial', '?'), count)

        all_satellites.sort(key=lambda x: current_load.get(x['_id'], 0))
        max_count = settings_vars.get_int(settings_vars.SATELLITE_MAX_RECIPIENTS_TO_SEND)
        for satellite in all_satellites:
            if satellite['enabled'] and satellite['paired']:
                # recipients_count = current_load.get(satellite['_id'], 0)
                yield self._send_recipients_to_satellite(satellite['serial'], max_count)
