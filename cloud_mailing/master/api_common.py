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
import email
import logging
from xmlrpclib import Fault
from datetime import datetime
import dateutil.parser

from twisted.web import http
from twisted.internet.threads import deferToThread
from .mailing_manager import MailingManager

from .models import Mailing, MAILING_STATUS

__author__ = 'Cedric RICARD'

log_cfg = logging.getLogger('config')
log_security = logging.getLogger('security')
log_api = logging.getLogger('api')


def set_mailing_properties(mailing_id, properties):
    mailing = Mailing.grab(mailing_id)
    if not mailing:
        raise Fault(http.NOT_FOUND, 'Mailing not found!')
    if mailing.status == MAILING_STATUS.FINISHED:
        raise Fault(http.FORBIDDEN, "Mailing properties can't be changed anymore. "
                                    "Only active mailings can be edited!")
    content_change = False
    for key, value in properties.items():
        if key == 'type':
            from models import mailing_types
            if value not in mailing_types:
                raise Fault(http.NOT_ACCEPTABLE, "Bad value '%s' for Property type. Acceptable values are (%s)"
                            % (value, ', '.join(mailing_types)))
            mailing.type = value
        elif key in (
                'sender_name', 'tracking_url', 'testing', 'backup_customized_emails', 'owner_guid', 'satellite_group'):
            setattr(mailing, key, value)
        elif key == 'shown_name':
            mailing.sender_name = value
        elif key in ('header', 'body'):
            setattr(mailing, key, value)
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
            msg['Subject'] = email.header.Header(subject, header_name='Subject')
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
                        raise email.errors.MessageParseError, "multipart/digest not supported"

                    elif subtype == 'parallel':
                        raise email.errors.MessageParseError, "multipart/parallel not supported"

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

        text = msg.as_string()
        p = text.find("\n\n")
        mailing.header = text[:p + 2]
        mailing.body = text[p + 2:]
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
    manager = MailingManager.getInstance()
    manager.forceToCheck()
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
        manager.close_mailing(mailing)
    else:
        deferToThread(manager.close_mailing, mailing)
    return mailing

def delete_mailing(mailing_id):
    mailing = close_mailing(mailing_id, sync=True)
    mailing.full_remove()
