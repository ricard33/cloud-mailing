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

"""
A toy email client.
"""
import argparse
import email
import logging
import os

import pwd

import grp

import requests
import twisted
from datetime import datetime

from twisted.cred import credentials
from twisted.mail._except import SMTPBadSender
from twisted.mail.protocols import ESMTPDomainDelivery
from twisted.python import failure
from twisted.python.log import PythonLoggingObserver
from twisted.python.util import switchUID
from zope.interface import implementer
from twisted.application import internet
from twisted.application import service
from twisted.internet import reactor

from twisted.internet import defer
from twisted.mail import smtp
from twisted.mail.imap4 import LOGINCredentials, PLAINCredentials

from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse, AllowAnonymousAccess, ICredentialsChecker
from twisted.cred.portal import IRealm, Portal, error

from ..common import http_status
from ..common.db_common import Db, get_db
from ..master.models import RECIPIENT_STATUS
from .. import __version__ as VERSION
from ..common import settings
from ..common.cm_logging import configure_logging
from ..common.ssl_tools import make_SSL_context

__author__ = 'Cedric RICARD'

log = logging.getLogger("smtpd")


@implementer(smtp.IMessageDelivery)
class ReturnPathMessageDelivery:

    def receivedHeader(self, helo, origin, recipients):
        return b"Received: ReturnPathMessageDelivery"

    def validateFrom(self, helo, origin):
        # All addresses are accepted
        return origin

    def validateTo(self, user):
        if b'-' in user.dest.local:
            ml_id, recipient_id = user.dest.local.split(b'-', 1)

            return lambda: ReturnPathMessage(ml_id, recipient_id)
        log.warning("Recipient '%s' refused: badly formated.", user)
        raise smtp.SMTPBadRcpt(user)


@implementer(smtp.IMessage)
class ReturnPathMessage:

    def __init__(self, ml_id, recipient_id):
        self.log = logging.getLogger('smtpd')
        self.ml_id = int(ml_id)
        self.recipient_id = recipient_id
        self.lines = []

    def lineReceived(self, line):
        self.lines.append(line)

    # @defer.inlineCallbacks
    def eomReceived(self):
        # print "New message received:"
        msg = "\n".join(self.lines)
        self.lines = None
        return self.handle_report(msg)

    def connectionLost(self):
        """
        Handle message truncated.

        semantics should be to discard the message
        """
        self.log.error("Connection lost")

    def handle_report(self, message_str):
        try:
            message = email.message_from_string(message_str)
            # print message['Content-Type']

            if message.get_content_type() == 'multipart/report':
                if message.get_param('report-type') == 'delivery-status':
                    delivery_status = message.get_payload(1)
                    # print delivery_status.as_string()
                    assert (delivery_status.get_content_type() == 'message/delivery-status')
                    per_message_status = delivery_status.get_payload()[0]
                    per_recipient_status = delivery_status.get_payload()[1]
                    action = per_recipient_status['Action']
                    recipient = per_recipient_status['Original-Recipient'] or per_recipient_status['Final-Recipient']
                    recipient = recipient.split(';')[1]
                    status = per_recipient_status['Status']
                    details = per_recipient_status['Diagnostic-Code']
                    # print 'Report found:'
                    # print '  action:', action
                    # print '  Recipient:', recipient
                    # print '  Status:', status
                    # print '  Details:', details
                    #
                    # print "######"

                    # print message.get_payload(2).as_string()
                    if action == 'failed':
                        self.log.info("Received failure notification for mailing [%d] recipient <%s>: %s", self.ml_id, recipient, details)
                        logging.getLogger('mailing.dsn').error("MAILING [%d] Delivery Status Notification for <%s>: %s",
                                                               self.ml_id, recipient, details)
                        # remove comment than MAY be present at the end of status line
                        status = status.split('(', 1)[0].strip()
                        return self.store_recipient_report(status, details, message_str)
                    self.log.warning("MAILING [%d] Received DSN with action %s for <%s>: %s",
                                  self.ml_id, action, recipient, details)

        except Exception as ex:
            self.log.exception("Error parsing received email")
            return defer.fail(failure.Failure(ex))

        return defer.succeed(None)

    @defer.inlineCallbacks
    def store_recipient_report(self,  status, details, full_report):
        db = get_db()
        # for p in [email, status, details, full_report]:
        #     print type(p),
        try:
            recipient = yield db.mailingrecipient.find_and_modify({'tracking_id': self.recipient_id, 'mailing.$id': self.ml_id},
                                              {'$set': {'send_status': RECIPIENT_STATUS.ERROR,
                                                        'reply_code': 550,
                                                        'reply_enhanced_code': status,
                                                        'reply_text': details,
                                                        'dsn': full_report,
                                                        'modified': datetime.utcnow()}
                                               })

            if recipient:
                update = {}
                previous_status = recipient['send_status']
                if previous_status == RECIPIENT_STATUS.FINISHED:
                    update = {'$inc': {'total_sent': -1, 'total_error': 1}}
                elif previous_status == RECIPIENT_STATUS.TIMEOUT:
                    update = {'$inc': {'total_error': 1}}
                elif previous_status in (RECIPIENT_STATUS.READY, RECIPIENT_STATUS.WARNING):
                    # DSN is received before satellite report...
                    update = {'$inc': {'total_pending': -1, 'total_error': 1}}
                else:
                    self.log.error("store_recipient_report: unexpected status '%s' for recipient '%s' on mailing [%d]",
                                   previous_status, self.recipient_id, self.ml_id)
                if update:
                    yield db.mailing.update({'_id': self.ml_id}, update)
            else:
                self.log.warning("Recipient '%s' not found in mailing [%d]", self.recipient_id, self.ml_id)

        except Exception as ex:
            self.log.error("Error trying to update recipient status: %s", ex)
            raise


class ExternalMessageDelivery(ESMTPDomainDelivery):
    def __init__(self, avatar, host=smtp.DNSNAME):
        super().__init__(service=None, user=avatar['avatarId'].decode(), host=host)
        self.avatar = avatar
        self.mail_from = None
        self.recipients = []

    def validateFrom(self, helo, origin):
        super().validateFrom(helo, origin)
        # check using external API
        response = requests.post(settings.SMTPD_VALIDATE_FROM_URL, json={
            settings.SMTPD_VALIDATE_FROM_FIELD: str(origin),
        }, headers=self.avatar['headers'], cookies=self.avatar['cookies'])
        if response.status_code != http_status.HTTP_200_OK:
            log.warning("Sender '%s' rejected by external API", origin)
            raise SMTPBadSender(origin)
        log.info("Sender '%s' accepted by external API", origin)
        self.mail_from = str(origin)
        return origin

    def validateTo(self, user):
        # check using external API
        response = requests.post(settings.SMTPD_VALIDATE_TO_URL, json={
            settings.SMTPD_VALIDATE_FROM_FIELD: self.mail_from,
            settings.SMTPD_VALIDATE_TO_FIELD: str(user),
        }, headers=self.avatar['headers'], cookies=self.avatar['cookies'])
        if response.status_code == http_status.HTTP_200_OK:
            log.info("Recipient '%s' accepted by external API", user)
            self.recipients.append(str(user))
            if len(self.recipients) == 1:
                # only first recipient return a real IMessage
                return lambda: ExternalMessage(self.mail_from, self.recipients, self.avatar)
            else:
                # for other, just a fake IMessage because all recipients are in first one
                return lambda: NullMessage()
        log.warning("Recipient '%s' refused by external API.", user)
        raise smtp.SMTPBadRcpt(user)


@implementer(smtp.IMessage)
class ExternalMessage:

    def __init__(self, mail_from, recipients, avatar):
        self.log = logging.getLogger('smtpd.ext')
        self.mail_from = mail_from
        self.recipients = recipients
        self.avatar = avatar
        self.lines = []

    def lineReceived(self, line):
        print("New line received:", line)
        self.lines.append(line)

    # @defer.inlineCallbacks
    def eomReceived(self):
        # print "New message received:"
        msg = b"\n".join(self.lines)
        self.lines = None
        return self.handle_message(msg)

    def connectionLost(self):
        """
        Handle message truncated.

        semantics should be to discard the message
        """
        self.log.error("Connection lost")

    def handle_message(self, message_str):
        # send message to external API
        try:
            log.info("Message received")
            response = requests.post(settings.SMTPD_MESSAGE_URL, json={
                settings.SMTPD_VALIDATE_FROM_FIELD: self.mail_from,
                settings.SMTPD_RECIPIENTS_FIELD: self.recipients,
                settings.SMTPD_MESSAGE_FIELD: message_str.decode(),
            }, headers=self.avatar['headers'], cookies=self.avatar['cookies'])
            response.raise_for_status()
            log.info("Message accepted by external API")

        except Exception as ex:
            self.log.exception("Error sending message to external API")
            return defer.fail(failure.Failure(ex))

        return defer.succeed(None)


@implementer(smtp.IMessage)
class NullMessage:

    def __init__(self):
        pass

    def lineReceived(self, line):
        pass

    def eomReceived(self):
        return defer.succeed(None)

    def connectionLost(self):
        pass


class SecureESMTP(smtp.ESMTP):
    def ext_STARTTLS(self, rest):
        super().ext_STARTTLS(rest)
        if self.startedTLS:
            self.challengers = {b"LOGIN": LOGINCredentials, b"PLAIN": PLAINCredentials}


class ReturnPathSMTPFactory(smtp.SMTPFactory):
    protocol = smtp.ESMTP

    def buildProtocol(self, addr):
        # from SMTP
        # p = self.protocol()
        p = SecureESMTP(
            # No auth if not in SSL
            # chal={b"LOGIN": LOGINCredentials, b"PLAIN": PLAINCredentials},
            contextFactory=make_SSL_context(),
        )
        p.factory = self
        # from ESMTP
        p.portal = self.portal
        p.host = self.domain
        #

        # patch for unauthenticated sessions
        p.delivery = ReturnPathMessageDelivery()
        return p


@implementer(IRealm)
class SimpleRealm:

    def requestAvatar(self, avatarId, mind, *interfaces):
        avatar = {}
        if isinstance(avatarId, dict):
            avatar = avatarId
            avatarId = avatar['avatarId']
        log.debug("requestAvatar(%s, %s)", avatarId, mind)
        # called only if client is authenticated
        if smtp.IMessageDelivery in interfaces:
            return smtp.IMessageDelivery, ExternalMessageDelivery(avatar), lambda: None
        raise NotImplementedError()


@implementer(ICredentialsChecker)
class ExternalApiChecker(object):
    """
    An credentials checker that use external REST API for check.

    """
    credentialInterfaces = (credentials.IUsernamePassword,
                            # credentials.IUsernameHashedPassword,
                            )

    def __init__(self, url, user_field='username', password_field='password', **kwargs):
        # self.users = {x.encode('ascii'):y for x, y in users.items()}
        self.url = url
        self.form = {}
        self.form.update(**kwargs)
        self.username_field = user_field
        self.password_field = password_field

    def _cbPasswordMatch(self, matched, username):
        if matched:
            return username
        else:
            return failure.Failure(error.UnauthorizedLogin())

    def requestAvatarId(self, credentials):
        log.debug("Checking authentication with %s", credentials)
        response = requests.post(settings.SMTPD_AUTH_URL, json={
            settings.SMTPD_AUTH_USERNAME_FIELD: credentials.username.decode(),
            settings.SMTPD_AUTH_PASSWORD_FIELD: credentials.password.decode()
        })
        response.raise_for_status()
        headers = {'accept': 'application/json'}
        headers['X-CSRFToken'] = response.cookies['csrftoken']
        headers['Referer'] = settings.SMTPD_AUTH_URL
        # Should return a string, but we need to keep cookies, so we return a dictionary
        return {'avatarId': credentials.username, 'headers': headers, 'cookies': response.cookies}
        # if credentials.username in self.users:
        #     return defer.maybeDeferred(
        #         credentials.checkPassword,
        #         self.users[credentials.username]).addCallback(
        #         self._cbPasswordMatch, credentials.username)
        # else:
        #     return defer.fail(error.UnauthorizedLogin())


def main(application=None):
    """
    SMTP daemon for receiving DSN (Delivery Status Notification)

    :param application: optional Application instance (if used inside twistd)
    :type application: twisted.application.service.Application
    """
    parser = argparse.ArgumentParser(description='Start the SMTPD process for CloudMailing.')
    parser.add_argument('-p', '--port', type=int, default=25, help='port number for SMTP (default: 25)')
    parser.add_argument('-u', '--uid', help='Change the UID of this process')
    parser.add_argument('-g', '--gid', help='Change the GID of this process')

    args = parser.parse_args()

    # Need to open TCP port early, before to switch user and configure log
    portal = Portal(SimpleRealm())
    portal.registerChecker(AllowAnonymousAccess())
    portal.registerChecker(ExternalApiChecker("api"))

    factory = ReturnPathSMTPFactory(portal)
    if application:
        smtpd = internet.TCPServer(args.port, factory)
        smtpd.setServiceParent(application)
    else:
        smtpd = reactor.listenTCP(args.port, factory)

    if args.uid or args.gid:
        uid = args.uid and pwd.getpwnam(args.uid).pw_uid or None
        gid = args.gid and grp.getgrnam(args.gid).gr_gid or None
        # for fname in os.listdir(settings.LOG_PATH):
        #     fullname = os.path.join(settings.LOG_PATH, fname)
        #     print fullname
        #     if args.uid:
        #         os.chown(fullname, args.uid, args.gid)
        switchUID(uid, gid)

    configure_logging("smtpd", settings.CONFIG_PATH, settings.LOG_PATH, settings.DEFAULT_LOG_FORMAT, False)

    ##Twisted logs
    observer = PythonLoggingObserver()
    observer.start()

    log = logging.getLogger("smtpd")

    log.info("****************************************************************")
    log.info("Starting CloudMailing SMTPD version %s" % VERSION )
    log.info("Serial: %s" % settings.SERIAL)
    log.info("Twisted version %s", twisted.version.short())
    log.info("****************************************************************")

    Db.getInstance(settings.MASTER_DATABASE, uri=settings.MASTER_DATABASE_URI)

    log.info("CM SMTPD started on port %d", args.port)


