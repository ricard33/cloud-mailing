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

import email
import logging
import time
from datetime import datetime
from xmlrpc.client import Fault

import dateutil.parser
import pymongo
from bson import SON
from twisted.internet.threads import deferToThread
from twisted.web import http

from ..common.encoding import force_bytes
from .models import MailingHourlyStats
from .mailing_manager import MailingManager
from .models import Mailing, MAILING_STATUS

__author__ = 'Cedric RICARD'

log_cfg = logging.getLogger('config')
log_security = logging.getLogger('security')
log_api = logging.getLogger('api')


def _check_dict_property(name, value, allowed_fields, mandatory_fields):
    params = {
        'name': name,
        'value': value,
        'allowed': allowed_fields,
        'mandatory': mandatory_fields
    }

    if not isinstance(value, dict):
        err_msg = "Bad value '%(value)s' for property '%(name)s'. It should be a dictionary." % params
        log_api.error(err_msg)
        raise Fault(http.NOT_ACCEPTABLE, err_msg)

    for key in list(value.keys()):
        if key not in allowed_fields:
            err_msg = "Bad value '%(value)s' for property '%(name)s'. " \
                      "Field '%(key)s is not allowed (allowed fields are '%(allowed)s')." \
                      % dict(params, **{'key': key})
            log_api.error(err_msg)
            raise Fault(http.NOT_ACCEPTABLE, err_msg)

    for key in mandatory_fields:
        if key not in value:
            err_msg = "Bad value '%(value)s' for property '%(name)s'. " \
                      "Field '%(key)s is missing (mandatory fields are '%(mandatory)s')." \
                      % dict(params, **{'key': key})
            log_api.error(err_msg)
            raise Fault(http.NOT_ACCEPTABLE, err_msg)



def set_mailing_properties(mailing_id, properties):
    mailing = Mailing.grab(mailing_id)
    if not mailing:
        log_api.error("set_mailing_properties: Mailing [%d] not found", mailing_id)
        raise Fault(http.NOT_FOUND, 'Mailing [%d] not found!' % mailing_id)
    if mailing.status == MAILING_STATUS.FINISHED:
        raise Fault(http.FORBIDDEN, "Mailing properties can't be changed anymore. "
                                    "Only active mailings can be edited!")
    content_change = False
    for key, value in list(properties.items()):
        if key == 'type':
            from .models import mailing_types
            if value not in mailing_types:
                raise Fault(http.NOT_ACCEPTABLE, "Bad value '%s' for Property type. Acceptable values are (%s)"
                            % (value, ', '.join(mailing_types)))
            mailing.type = value
        elif key in (
            'sender_name', 'tracking_url', 'testing', 'backup_customized_emails', 'owner_guid', 'satellite_group',
            'url_encoding'
        ):
            setattr(mailing, key, value)
        elif key == 'dkim':
            allowed_fields = ('enabled', 'selector', 'domain', 'privkey', 'identity', 'canonicalize', 'signature_algorithm',
                              'include_headers', 'length')
            mandatory_fields = ('selector', 'domain', 'privkey')
            _check_dict_property(key, value, allowed_fields, mandatory_fields)
            setattr(mailing, key, value)
        elif key == 'shown_name':
            mailing.sender_name = value
        elif key == 'header':
            mailing.header = force_bytes(value).strip() + b'\n\n'
            if key == 'header':
                message = mailing.get_message()
                mailing.subject = message.get('Subject')
        elif key == 'body':
            mailing.body = force_bytes(value)
        elif key in ('dont_close_if_empty', 'read_tracking', 'click_tracking'):
            setattr(mailing, key, bool(value))
        elif key == 'mail_from':
            mailing.mail_from = value
            mailing.domain_name = value.split('@')[1]
        elif key in ('scheduled_start', 'scheduled_end'):
            setattr(mailing, key, value and dateutil.parser.parse(value) or None)
        elif key == 'scheduled_duration':
            i = int(value)
            mailing.scheduled_duration = i and i or None
        elif key in ('subject', 'html_content', 'plain_content'):
            if 'charset' not in properties:
                raise Fault(http.NOT_ACCEPTABLE,
                            "Missing charset field. This field is mandatory for 'subject', 'html_content' and 'plain_content' fields.")
            content_change = True
        elif key == 'charset':
            # ignored, only used with subject, html_content and plain_content fields
            pass
        else:
            raise Fault(http.NOT_ACCEPTABLE, "Property '%s' is unknown or can't be changed." % key)
    if content_change:
        msg = mailing.get_message()

        charset = properties.get('charset')
        subject = properties.get('subject')
        html_content = properties.get('html_content')
        plain_content = properties.get('plain_content')
        if subject is not None:
            if 'Subject' in msg:
                del msg['Subject']
            msg['Subject'] = subject
            mailing.subject = subject

        if html_content or plain_content:
            def replace_bodies(part, html_content, plain_content):
                import email.message
                assert (isinstance(part, email.message.Message))
                if part.is_multipart():
                    subtype = part.get_content_subtype()
                    if subtype == 'mixed':
                        replace_bodies(part.get_payload(0), html_content, plain_content)

                    elif subtype == 'alternative':
                        for p in part.get_payload():
                            replace_bodies(p, html_content, plain_content)

                    elif subtype == 'digest':
                        raise email.errors.MessageParseError("multipart/digest not supported")

                    elif subtype == 'parallel':
                        raise email.errors.MessageParseError("multipart/parallel not supported")

                    elif subtype == 'related':
                        replace_bodies(part.get_payload(0), html_content, plain_content)

                    else:
                        log_api.warn("Unknown multipart subtype '%s'" % subtype)

                else:
                    maintype, subtype = part.get_content_type().split('/')
                    if maintype == 'text':
                        new_content = None
                        if subtype == 'plain' and plain_content is not None:
                            new_content = plain_content
                        elif subtype == 'html' and html_content is not None:
                            new_content = html_content
                        if new_content is not None:
                            # to force content to be correctly encoded
                            if 'Content-Transfer-Encoding' in part:
                                del part['Content-Transfer-Encoding']
                            part.set_payload(new_content, charset=charset)
                    else:
                        log_api.warn("personalise_bodies(): can't handle '%s' parts" % part.get_content_type())

            replace_bodies(msg, html_content, plain_content)

        # store new message
        # convert_email_charset(msg)

        msg_bytes = msg.as_bytes()
        p = msg_bytes.find(b"\n\n")
        mailing.header = msg_bytes[:p + 2]
        mailing.body = msg_bytes[p + 2:]
    mailing.save()
    from .cloud_master import mailing_portal
    if mailing_portal:
        mailing_master = mailing_portal.realm
        mailing_master.invalidate_mailing_content_on_satellites(mailing)
    return mailing


def start_mailing(mailing_id):
    mailing = Mailing.grab(mailing_id)
    if not mailing:
        log_api.warn("Mailing [%d] not found!", mailing_id)
        raise Fault(http.NOT_FOUND, 'Mailing not found!')
    if mailing.status == MAILING_STATUS.PAUSED:
        if mailing.start_time:  ## only set when mailing changes its state to RUNNING
            mailing.status = MAILING_STATUS.RUNNING
        else:
            mailing.status = MAILING_STATUS.READY
        mailing.save()
    else:
        mailing.activate()
    return mailing


def pause_mailing(mailing_id):
    mailing = Mailing.grab(mailing_id)
    if not mailing:
        log_api.warn("Mailing [%d] not found!", mailing_id)
        raise Fault(http.NOT_FOUND, 'Mailing not found!')

    if mailing.status in (MAILING_STATUS.READY, MAILING_STATUS.RUNNING, MAILING_STATUS.PAUSED):
        mailing.status = MAILING_STATUS.PAUSED
        mailing.save()
        manager = MailingManager.getInstance()
        assert(isinstance(manager, MailingManager))
        deferToThread(manager.pause_mailing, mailing)
    else:
        log_api.error("Bad mailing status: '%s' for [%d]. Can't pause it!", mailing.status, mailing_id)
        raise Fault(http.NOT_ACCEPTABLE, "Bad mailing status: '%s'. Can't pause it!" % mailing.status)
    return mailing


def close_mailing(mailing_id, sync=False):
    mailing = Mailing.grab(mailing_id)
    if not mailing:
        log_api.warn("Mailing [%d] not found!", mailing_id)
        raise Fault(http.NOT_FOUND, 'Mailing not found!')

    mailing.status = MAILING_STATUS.FINISHED
    mailing.save()
    manager = MailingManager.getInstance()
    assert(isinstance(manager, MailingManager))
    if sync:
        manager.close_mailing(mailing.id)
    else:
        deferToThread(manager.close_mailing, mailing.id)
    return mailing

def delete_mailing(mailing_id):
    mailing = close_mailing(mailing_id, sync=True)
    mailing.full_remove()


def compute_hourly_stats(filter, from_date, to_date):
    """
    Returns all stats for every hour between two dates. If statistics don't exist for a given hour, it is created with
    empty values.
    So this is warranty to have an entry for every hours.
    :param filter: DB filter
    :param from_date: begin datetime
    :param to_date: end datetime
    :return: an array of hourly statistics
    """
    all_stats = []
    current_epoch_hour = int((from_date - datetime(1970, 1, 1)).total_seconds() / 3600)
    max_epoch_hour = int((to_date - datetime(1970, 1, 1)).total_seconds() / 3600)
    max_epoch_hour = min(int(time.time() / 3600), max_epoch_hour)

    def fill_until(all_stats, epoch_hour, next_epoch_hour):
        while epoch_hour < next_epoch_hour:
            stats = {
                'date': datetime.utcfromtimestamp(epoch_hour * 3600),
                'epoch_hour': epoch_hour,
                'sent': 0,
                'failed': 0,
                'tries': 0,
            }
            # print stats
            all_stats.append(stats)
            epoch_hour += 1
        return epoch_hour

    # for s in MailingHourlyStats.find(filter).sort((('epoch_hour', pymongo.ASCENDING), ('sender', pymongo.ASCENDING))):
    for s in MailingHourlyStats._get_collection().aggregate([
        {'$match': filter},
        {'$group': {
            '_id': '$epoch_hour',
            'date': {'$first': '$date'},
            'sent': {'$sum': '$sent'},
            'failed': {'$sum': '$failed'},
            'tries': {'$sum': '$tries'},
        }},
        {'$sort': SON([('_id', pymongo.ASCENDING), ('sender', pymongo.ASCENDING)])},
    ]):
        # print "AGGREGATE:", s
        current_epoch_hour = fill_until(all_stats, current_epoch_hour, s['_id'])
        stats = {
            # 'sender': s.sender,
            'date': s['date'],
            # 'epoch_hour': s.epoch_hour,
            'epoch_hour': s['_id'],
            'sent': s['sent'],
            'failed': s['failed'],
            'tries': s['tries'],
        }
        # print stats
        all_stats.append(stats)
        current_epoch_hour += 1
    fill_until(all_stats, current_epoch_hour, max_epoch_hour + 1)
    # print len(all_stats)
    # print all_stats[:100]
    return all_stats
