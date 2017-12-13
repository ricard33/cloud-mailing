# Copyright 2015 Cedric RICARD
#
# This file is part of CloudMailing.
#
# CloudMailing is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CloudMailing is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with CloudMailing.  If not, see <http://www.gnu.org/licenses/>.

import pickle as pickle
import logging
import re
import time
from datetime import datetime

import pymongo
import txmongo.filter
from bson import DBRef
from twisted.internet import defer
from twisted.spread import util

from ..common.db_common import get_db
from ..common.singletonmixin import Singleton
from . import settings_vars
from .models import MAILING_STATUS, RECIPIENT_STATUS

__author__ = 'Cedric RICARD'


class SendRecipientsTask(Singleton):
    def __init__(self):
        self.log = logging.getLogger("send_rcpts")

    # @staticmethod
    # @defer.inlineCallbacks
    # def _make_get_recipients_queryset(db, satellite_group, domain_affinity, log):
    #     """Return a pymongo cursor"""
    #     included, excluded = SendRecipientsTask._handle_domain_affinity(domain_affinity, log)
    #     mailing_filter = {
    #         'status': {'$in': [MAILING_STATUS.FILLING_RECIPIENTS,  # For Test recipients
    #                            MAILING_STATUS.READY,  # For Test recipients
    #                            MAILING_STATUS.RUNNING]},
    #         'satellite_group': satellite_group
    #     }
    #     _list_of_mailings = yield db.mailing.find(mailing_filter, fields=[])
    #     mailing_ids = map(lambda x: x['_id'], _list_of_mailings)
    #     query = {
    #         '$and': [{'$or': [{'next_try': {'$lte': datetime.utcnow()}},
    #                           {'next_try': None}]},
    #                  {'$or': [{'in_progress': False}, {'in_progress': None}]},
    #                  # {'cloud_client': None},
    #                  ],
    #         'send_status': {'$in': (RECIPIENT_STATUS.READY,
    #                                 RECIPIENT_STATUS.WARNING),},
    #         'mailing.$id': {'$in': mailing_ids},
    #     }
    #     if included and excluded:
    #         query['$and'].extend([
    #             {'domain_name': {'$in': included}},
    #             {'domain_name': {'$nin': excluded}},
    #         ])
    #     elif included:
    #         query['domain_name'] = {'$in': included}
    #     elif excluded:
    #         query['domain_name'] = {'$nin': excluded}
    #     defer.returnValue(query)

    @staticmethod
    def _handle_domain_affinity(domain_affinity, log):
        included = []
        excluded = []
        try:
            domain_re = re.compile('^(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?$', re.IGNORECASE)
            if domain_affinity and isinstance(domain_affinity, dict):
                if domain_affinity.get('enabled', True):
                    for domain in domain_affinity.get('include', []):
                        if not domain_re.match(domain):
                            log.warning("Wrong domain name format for '%s'. Ignored...", domain)
                            continue
                        included.append(domain)
                    for domain in domain_affinity.get('exclude', []):
                        if not domain_re.match(domain):
                            log.warning("Wrong domain name format for '%s'. Ignored...", domain)
                            continue
                        excluded.append(domain)

            elif isinstance(domain_affinity, str):
                affinity = domain_affinity and eval(domain_affinity)

                if affinity:
                    if not isinstance(affinity, dict):
                        raise TypeError("Affinity is not a dictionary!")
                    # print self.cloud_client.serial, repr(affinity)
                    if affinity.get('enabled', True):
                        for domain, value in list(affinity.items()):
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
        return included, excluded

    def _get_avatar(self, serial):
        from .cloud_master import mailing_portal

        if mailing_portal:
            mailing_master = mailing_portal.realm
            return mailing_master.avatars.get(serial)
        else:
            self.log.error("Can't get MailingPortal object!")

    @staticmethod
    def make_mailings_queryset(satellite_group=None):
        now = datetime.utcnow()
        filter = {
            '$and': [
                {'$or': [{'scheduled_start': {'$lte': now}},
                         {'scheduled_start': None}]},
                {'$or': [{'scheduled_end': {'$gt': now}},
                         {'scheduled_end': None}]},
            ],
            'status': {'$in': (MAILING_STATUS.READY, MAILING_STATUS.RUNNING)},
            'satellite_group': satellite_group,
        }

        return filter

    @staticmethod
    def make_recipients_queryset(mailing_id, included_domains=None, excluded_domains=None, only_primary=False):
        query = {
            '$and': [
                {'$or': [{'next_try': {'$lte': datetime.utcnow()}},
                         {'next_try': None}]},
                {'$or': [{'in_progress': False}, {'in_progress': None}]},
            ],
            'send_status': {'$in': (RECIPIENT_STATUS.READY,
                                    RECIPIENT_STATUS.WARNING),},
            'mailing.$id': mailing_id,
        }
        if included_domains and excluded_domains:
            query['$and'].extend([
                {'domain_name': {'$in': included_domains}},
                {'domain_name': {'$nin': excluded_domains}},
            ])
        elif included_domains:
            query['domain_name'] = {'$in': included_domains}
        elif excluded_domains:
            query['domain_name'] = {'$nin': excluded_domains}
        if only_primary:
            query['primary'] = True
        return query

    @defer.inlineCallbacks
    def filling_primary_recipients(self, db, nb_recipients, satellite_group, included, excluded):
        mailing_filter = {
            'status': {'$in': [MAILING_STATUS.FILLING_RECIPIENTS,  # For Test recipients
                               MAILING_STATUS.READY,  # For Test recipients
                               MAILING_STATUS.RUNNING]},
            'satellite_group': satellite_group
        }
        _list_of_mailings = yield db.mailing.find(mailing_filter, fields=[])
        mailing_ids = [x['_id'] for x in _list_of_mailings]

        filter = SendRecipientsTask.make_recipients_queryset({'$in': mailing_ids}, included, excluded, only_primary=True)
        f = txmongo.filter.sort(txmongo.filter.ASCENDING("next_try"))
        selected_recipients = yield db.mailingrecipient.find(filter, filter=f, limit=nb_recipients)

        # not optimized at all, but primary recipients should be very rare
        for recipient in selected_recipients:
            mailing = yield db.mailing.find_one({'_id': recipient['mailing'].id})
            recipient['mail_from'] = mailing['mail_from']
            recipient['sender_name'] = mailing['sender_name']

        defer.returnValue(selected_recipients)

    @defer.inlineCallbacks
    def filling_mailing_queue(self, nb_recipients, satellite_group, domain_affinity):
        self.log.debug("Starting filling mailing queue...")

        max_nb_recipients = nb_recipients
        recipients = []
        t0 = time.time()
        count = 0
        try:
            db = get_db()

            mailing_filter = SendRecipientsTask.make_mailings_queryset(satellite_group)
            results = yield db.mailing.aggregate([
                {'$match': mailing_filter},
                {'$group': {'_id': None, 'sum': {'$sum': '$total_pending'}}}
            ])
            total_recipients_pending = results and results[0].get('sum', 0) or 0

            included, excluded = SendRecipientsTask._handle_domain_affinity(domain_affinity, self.log)

            t1 = time.time()
            recipients = yield self.filling_primary_recipients(db, nb_recipients, satellite_group, included, excluded)
            self.log.debug("Filling mailing queue: selected %d primary recipients (in %.1f seconds)",
                           len(recipients), time.time() - t1)
            nb_recipients -= len(recipients)

            if total_recipients_pending:
                mailings = yield db.mailing.find(mailing_filter, fields=['status', 'start_time', 'total_pending',
                                                                         'mail_from', 'sender_name'])
                for mailing in mailings:
                    if max_nb_recipients <= len(recipients):
                        self.log.warning("Filling mailing queue: max recipients reached. Skipping others mailings.")
                        # TODO ALERT here
                        break
                    if mailing['status'] == MAILING_STATUS.READY:
                        yield db.mailing.update({'_id': mailing['_id']}, {'$set': {
                            'status': MAILING_STATUS.RUNNING,
                            'start_time': datetime.utcnow(),
                        }})
                    nb_max = max(100, mailing.get('total_pending', 0)
                                 * nb_recipients / total_recipients_pending)
                    nb_max = int(min(nb_max, max_nb_recipients - len(recipients)))
                    if nb_max <= 0:
                        self.log.error("Filling mailing queue: nb_max has to be strictly greater than 0! Logic error!")
                        break
                    # print "nb_max = %d" % nb_max
                    self.log.debug("Filling mailing queue: selecting max %d recipients from mailing [%d]", nb_max,
                                   mailing['_id'])
                    filter = SendRecipientsTask.make_recipients_queryset(mailing['_id'], included, excluded)
                    t1 = time.time()
                    f = txmongo.filter.sort(txmongo.filter.ASCENDING("next_try"))
                    selected_recipients = yield db.mailingrecipient.find(filter, filter=f, limit=nb_max)
                    for recipient in selected_recipients:
                        recipient['mail_from'] = mailing['mail_from']
                        recipient['sender_name'] = mailing['sender_name']

                    count += len(selected_recipients)
                    self.log.debug("Filling mailing queue: selected %d recipients from mailing [%d] (in %.1f seconds)",
                                   len(selected_recipients), mailing['_id'], time.time() - t1)
                    recipients.extend(selected_recipients)

            if count:
                self.log.info("Mailing queue successfully filled %d recipients in %.1f seconds.", count,
                              time.time() - t0)
        except:
            self.log.exception("Exception using Filling Mailing Queue function.")
            defer.returnValue(recipients)
        defer.returnValue(recipients)

    @defer.inlineCallbacks
    def _get_recipients(self, count, serial):
        self.log.debug("_get_recipients(client=%s, count=%d)", serial, count)
        db = get_db()

        cloud_client = yield db.cloudclient.find_one({'serial': serial})

        if not cloud_client:
            self.log.warning("_send_recipients_to_satellite() Unknown client [%s]", serial)
            return
        if not cloud_client['enabled']:
            self.log.warning("_send_recipients_to_satellite() refused for disabled client [%s]", serial)
            return
        domain_affinity = cloud_client.get('domain_affinity')
        satellite_group = cloud_client.get('group')
        # query_filter = yield self._make_get_recipients_queryset(db, satellite_group,
        #                                                         domain_affinity, self.log)
        # f = txmongo.filter.sort(txmongo.filter.ASCENDING("next_try"))
        # queue = yield db.mailingrecipient.find(query_filter, filter=f, limit=count)
        queue = yield self.filling_mailing_queue(count, satellite_group, domain_affinity)
        recipients = []
        ids = []
        for rcpt in queue:
            try:
                for key in ('cloud_client', 'in_progress', 'read_time'):
                    rcpt.pop(key, None)
                rcpt['mailing'] = rcpt['mailing'].id
                recipients.append(rcpt)
                ids.append(rcpt['_id'])
            except:
                self.log.exception("Error preparing recipient '%s'...", rcpt['email'])

        update_item = {'$set': {
            'cloud_client': serial,
            'date_delegated': datetime.utcnow(),
            'in_progress': True,
        }}
        r = yield db.mailingrecipient.update_many({'_id': {'$in': ids}}, update_item)
        defer.returnValue(recipients)

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
            self.log.debug("_send_recipients_to_satellite(%s) Client is already full.", serial)
            return

        recipients = yield self._get_recipients(min(count, wanted_count), serial)

        def show_time_at_end(_t0, rcpts_count, data_len):
            self.log.debug("_send_recipients_to_satellite(%s): Sent %d recipients (%.2f Kb) in %.2f s",
                           serial, rcpts_count, data_len / 1024.0, time.time() - _t0)

        self.log.debug("_send_recipients_to_satellite(%s): starting sending %d recipients at %.2f s",
                       serial, len(recipients), time.time() - t0)
        data = pickle.dumps(recipients)
        util.StringPager(collector, data, 262144, show_time_at_end, t0, len(recipients), len(data))

    @defer.inlineCallbacks
    def run(self):
        try:
            db = get_db()

            # all_satellites = yield db.cloudclient.find({'enabled': True, 'paired': True})
            all_satellites = yield db.cloudclient.find()
            current_load = yield db.mailingrecipient.aggregate([
                {
                    '$match': {'in_progress': True,}
                },
                {
                    '$group': {
                        '_id': '$cloud_client',
                        'count': {'$sum': 1}
                    }
                },
                {'$sort': {'count': pymongo.DESCENDING}}
            ])
            current_load = {load['_id']: load['count'] for load in current_load}
            self.log.debug("Current satellite load:")
            for _id, count in list(current_load.items()):
                self.log.debug("    - %s: %d recipients", _id, count)

            all_satellites.sort(key=lambda x: current_load.get(x['serial'], 0))
            max_count = settings_vars.get_int(settings_vars.SATELLITE_MAX_RECIPIENTS_TO_SEND)
            for satellite in all_satellites:
                if satellite.get('enabled') and satellite.get('paired'):
                    # recipients_count = current_load.get(satellite['serial'], 0)
                    yield self._send_recipients_to_satellite(satellite['serial'], max_count)

        except:
            self.log.exception("Exception in SendRecipientsTask.run() function.")
