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

from datetime import datetime
from twisted.internet import defer
from twisted.python import failure

import import_cm_path
from cloud_mailing.common import settings
from cloud_mailing.common.db_common import get_db, Db
from cloud_mailing.master.models import RECIPIENT_STATUS

Db.getInstance(settings.MASTER_DATABASE)


def handle_report(message_str, mailing_ids):
    try:
        message = email.message_from_string(message_str)
        # print message['Content-Type']

        if message.get_content_type() == 'multipart/report':
            # print "Yea! Report found..."
            if message.get_param('report-type') == 'delivery-status':
                # print "Double yea !!! Delivery status found..."
                delivery_status = message.get_payload(1)
                # print delivery_status.as_string()
                assert(delivery_status.get_content_type() == 'message/delivery-status')
                per_message_status = delivery_status.get_payload()[0]
                per_recipient_status = delivery_status.get_payload()[1]
                action = per_recipient_status['Action']
                recipient = per_recipient_status['Original-Recipient'] or per_recipient_status['Final-Recipient']
                recipient = recipient.split(';')[1]
                status = per_recipient_status['Status']
                details = per_recipient_status['Diagnostic-Code']
                print 'Report found:'
                print '  action:', action
                print '  Recipient:', recipient
                print '  Status:', status
                print '  Details:', details

                print "######"

                # print message.get_payload(2).as_string()

                return store_recipient_report(recipient, status, details, message_str, mailing_ids)

    except Exception as ex:
        print ex
        return defer.fail(failure.Failure(ex))

    return defer.succeed(None)


def store_recipient_report(email, status, details, full_report, mailing_ids):
    db = get_db()
    return db.mailingrecipient.update({'email': email, 'mailing.$id': {'$in': mailing_ids}},
                                     {'$set': {'send_status': RECIPIENT_STATUS.ERROR,
                                               'reply_code': 550,
                                               'reply_enhanced_code': status,
                                               'reply_text': details,
                                               'dsn': full_report,
                                               'modified': datetime.utcnow()}
                                      },
                                     multi=True).\
        addCallbacks(cb_update_recipient, eb_update_recipient)


def cb_update_recipient(result):
    print(result)
    return result


def eb_update_recipient(err):
    print("Error trying to update recipient status: %s" % err)
    return err


def onError(err):
    print err
    return err