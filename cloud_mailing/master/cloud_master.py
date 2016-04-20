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

import cPickle as pickle
import exceptions
import logging
import os
import time
from datetime import datetime, timedelta

import pymongo
from bson import ObjectId
from twisted.cred import checkers, portal, error as cred_error, credentials
from twisted.internet import reactor, defer
from twisted.internet.threads import deferToThreadPool
from twisted.python import failure
from twisted.python import threadpool
from twisted.python.deprecate import deprecated
from twisted.python.versions import Version
from twisted.spread import pb, util
from twisted.spread.util import CallbackPageCollector
from zope.interface import implements

from cloud_mailing.master import settings_vars
from .models import CloudClient, Mailing, SenderDomain
from .models import RECIPIENT_STATUS, MAILING_STATUS
from ..common import settings
from ..common.db_common import get_db

mailing_portal = None
unit_test_mode = False   # used to make delays shorter

#pylint: disable-msg=W0404

def make_customized_file_name(mailing_id, recipient_id):
    """compose the filename where the customized email is stored."""
    # this name should be the same as in satellite to allow smart optimization with local satellite
    return 'cust_ml_%d_rcpt_%s.rfc822' % (mailing_id, str(recipient_id))

def getAllPages(referenceable, methodName, *args, **kw):
    """
    A utility method that will call a remote method which expects a
    PageCollector as the first argument.

    This version is an improved one from twisted, with an errback called in case of error.
    """
    d = defer.Deferred()
    referenceable.callRemote(methodName, CallbackPageCollector(d.callback), *args, **kw).addErrback(d.errback)
    return d


__new_recipients_threadpool = None

def get_new_recipients_threadpool():
    global __new_recipients_threadpool
    if __new_recipients_threadpool is None:
        __new_recipients_threadpool = threadpool.ThreadPool(1, 1, "cm.get_new_recipients")
        __new_recipients_threadpool.start()
    return __new_recipients_threadpool

__reports_threadpool = None

def get_reports_threadpool():
    global __reports_threadpool
    if __reports_threadpool is None:
        __reports_threadpool = threadpool.ThreadPool(1, 1, "cm.send_reports")
        __reports_threadpool.start()
    return __reports_threadpool


def stop_all_threadpools():
    global __new_recipients_threadpool, __reports_threadpool
    if __new_recipients_threadpool:
        __new_recipients_threadpool.stop()
        __new_recipients_threadpool = None
    if __reports_threadpool:
        __reports_threadpool.stop()
        __reports_threadpool = None


class ClientAvatar(pb.Avatar):
    """
    Master uses this avatar to access to client's services.
    """
    def __init__(self, cloud_client):
        self.name = cloud_client.serial
        self.cloud_client = cloud_client
        self.clients = []
        self.mailing_manager = None

    def attached(self, mind, avatarId):
        assert(isinstance(avatarId, CloudClient))
        assert(avatarId == self.cloud_client)
        avatarId.paired = True
        avatarId.date_paired = datetime.utcnow()
        avatarId.save()
        self.clients.append(mind)
        # print "attached to", mind, avatarId

    def detached(self, mind):
        self.cloud_client = CloudClient.grab(self.cloud_client.id)  # reload object
        self.cloud_client.paired = False
        self.cloud_client.date_paired = datetime.utcnow()
        self.cloud_client.save()
        self.clients.remove(mind)
        # print "detached from", mind

    def update(self, message):
        for c in self.clients:
            c.callRemote("update", message)

    def activate_unittest_mode(self, activated=True):
        global unit_test_mode
        unit_test_mode = activated
        for c in self.clients:
            logging.debug("Calling activate_unittest_mode() for %s", c)
            c.callRemote("activate_unittest_mode", activated)

    def close_mailing(self, mailing):
        """Ask clients to close a mailing and immediately stops to send any related email."""
        for c in self.clients:
            c.callRemote("close_mailing", mailing.id)

    def invalidate_mailing_body(self, mailing):
        """Informs satellite that mailing content has changed."""
        for c in self.clients:
            c.callRemote("mailing_changed", mailing.id)

    def get_recipients_list(self):
        """
        Ask the client to returns the list of currently handled recipient ids.
        :returns: a Deferred which will be fired when the result of
                  this remote call is received.
        """
        l = []
        for c in self.clients:
            l.append(c.callRemote("get_recipients_list"))

        def _get_recipients_list_cb(results):
            ids = []
            for result in results:
                if result[0]:
                    ids.extend(result[1])
            return ids
        return defer.DeferredList(l, fireOnOneErrback=True, consumeErrors=True)\
                    .addCallback(_get_recipients_list_cb)

    def check_recipients(self, recipients):
        """
        Ask the client to returns a dictionary mapping for each input id the corresponding recipient object, nor None is not found.

        :param recipients: array of recipient_id
        :type recipients: list
        :returns: a Deferred which will be fired when the result of
                  this remote call is received.
        """
        l = []
        for c in self.clients:
            l.append(c.callRemote("check_recipients", recipients))

        def _check_recipients_cb(results, *args):
            recipients_dict = {}
            for result in results:
                if result[0]:
                    recipients_dict.update(result[1])
            return recipients_dict
        return defer.DeferredList(l, fireOnOneErrback=True, consumeErrors=True)\
                    .addCallback(_check_recipients_cb)

    def retrieve_customized_content(self, mailing_id, recipient_id):
        if self.clients:
            return getAllPages(self.clients[0], 'get_customized_content', mailing_id, recipient_id)
        return defer.fail()

    def prepare_getting_recipients(self, count):
        """
        Ask satellite for how many recipients he want, and for its paging collector.
        The satellite should return a tuple (wanted_count, collector)
        :param count: proposed recipients count
        :return: a deferred
        """
        if self.clients:
            return self.clients[0].callRemote('prepare_getting_recipients', count)
        return defer.fail()

    def perspective_get_mailing_manager(self, satellite_config=None):
        # maybe insert here more rights management
        if satellite_config:
            self.cloud_client = CloudClient.grab(self.cloud_client.id)  # reload object
            self.cloud_client.version = satellite_config.get('version')
            self.cloud_client.settings = satellite_config.get('settings')
            self.cloud_client.save()
        if not self.mailing_manager:
            self.mailing_manager = MailingManagerView(self.cloud_client)
        return self.mailing_manager


class MailingManagerView(pb.Viewable):
    """
    Contains master's services available for clients.
    """
    def __init__(self, cloud_client):
        assert(isinstance(cloud_client, CloudClient))
        self.cloud_client = cloud_client
        self.log = logging.getLogger('ml_manager.%d' % cloud_client._id)
        self.log.info("CLOUD CLIENT [%d] connected with serial '%s'", cloud_client._id, cloud_client.serial)

    def view_get_mailing(self, client, collector, mailing_id):
        """
        Returns the mailing content as a dictionary:
            - id: mailing_id (Mandatory)
            - header: email headers(string)
            - body: email body (string)
            - tracking_url: base url for all tracking links
            - delete: True if the mailing should be deleted on slave.
        """
        self.log.debug("get_mailing(%s)", mailing_id)
        from models import Mailing
        self.cloud_client = CloudClient.grab(self.cloud_client.id)  # reload object
        if not self.cloud_client.enabled:
            self.log.warn("get_mailing() refused for disabled client [%s]", self.cloud_client.serial)
            raise pb.Error("Not allowed!")
        try:
            mailing = Mailing.find_one({'_id': mailing_id,
                                        'status': {'$in': (MAILING_STATUS.FILLING_RECIPIENTS,
                                                           MAILING_STATUS.READY,
                                                           MAILING_STATUS.RUNNING)}})
            if mailing:
                header = str(mailing.header).replace('\r\n', '\n')
                body = mailing.body.replace('\r\n', '\n')
                feedback_loop = mailing.feedback_loop or settings_vars.get(settings_vars.FEEDBACK_LOOP_SETTINGS)
                dkim = mailing.dkim
                if not dkim:
                    self.log.debug("No DKIM for mailing [%d]. Looking configuration for domain '%s'...", mailing_id, mailing.domain_name)
                    sender_domain = SenderDomain.find_one({'domain_name': mailing.domain_name})
                    if sender_domain:
                        self.log.debug("Found DKIM configuration for domain '%s'", mailing.domain_name)
                        dkim = sender_domain.dkim
                util.StringPager(collector, pickle.dumps({'id': mailing_id,
                                                          'header': header,
                                                          'body': body,
                                                          'read_tracking': mailing.read_tracking,
                                                          'click_tracking': mailing.click_tracking,
                                                          'tracking_url': mailing.tracking_url,
                                                          'backup_customized_emails': mailing.backup_customized_emails,
                                                          'testing': mailing.testing,
                                                          'dkim': dkim,
                                                          'feedback_loop': feedback_loop,
                                                          'domain_name': mailing.domain_name,
                                                          'type': mailing.type,
                                                          'delete': False}))
            else:
                self.log.error("Mailing [%d] doesn't exist anymore.", mailing_id)
                util.StringPager(collector, pickle.dumps({'id': mailing_id, 'delete': True}))
        except Exception:
            self.log.exception("Can't get mailing [%d]", mailing_id)
            util.StringPager(collector, pickle.dumps({'id': mailing_id, 'delete': True}))
        #self.log.debug("get_mailing(%d) finished", mailing_id)

    @deprecated(Version('cloud_mailing', 0, 5, 2),
                "twisted.internet.defer.inlineCallbacks")
    def view_get_recipients(self, client, collector, count=1):
        """
        Returns an array of recipients. Each recipient is described by a dictionary with all its attributes.
        """
        self.log.warning("get_recipients(count=%d) DEPRECATED", count)
        data = pickle.dumps([])
        util.StringPager(collector, data)

    # @defer.inlineCallbacks
    def view_get_my_recipients(self, client, collector):
        """
        Returns an array of recipient ids already handled by the connected client. Used by clients to verify validity of
         their recipients list on reconnection (in case of orphan purge when it was offline).
        """
        self.log.debug("get_my_recipients() for '%s'", self.cloud_client.serial)
        db = get_db()
        recipients = yield db.mailingrecipient.find_many({'cloud_client': self.cloud_client.serial}, fields=[])
        # recipients = list(recipients)
        data = pickle.dumps(map(lambda r: str(r['_id']), recipients))
        # print "sending %d length data for %d recipients" % (len(data), len(recipients))
        util.StringPager(collector, data)

    @staticmethod
    def _store_reports(_recipients, serial, log):
        from models import MailingRecipient
        t0 = time.time()

        # We need to keep backup_customized_emails flag for each mailing to avoid consuming requests
        mailing_ids = [recipient['mailing'] for recipient in _recipients]
        mailings = {}
        for ml in Mailing._get_collection().find({'_id': {'$in': mailing_ids}}, {'backup_customized_emails': True}):
            mailings[ml['_id']] = ml

        ids_ok = []
        mailings_stats = {}
        # TODO optimize this using UPDATE multiples
        for rcpt in _recipients:
            name = "Unknown"
            try:
                name = rcpt['email']
                recipient = MailingRecipient.grab(rcpt['_id'])
                if recipient is None:
                    log.warn("Can't update recipient '%s'. Mailing [%d] or recipient doesn't exist anymore.", name, rcpt['mailing'])
                else:
                    assert(isinstance(recipient, MailingRecipient))
                    recipient.report_ready = True
                    if not recipient.first_try:
                        recipient.first_try = rcpt['first_try']
                    was_in_softbounce = recipient.send_status == RECIPIENT_STATUS.WARNING
                    recipient.try_count = rcpt['try_count']
                    recipient.update_send_status(rcpt['send_status'],
                                                 rcpt['reply_code'],
                                                 rcpt['reply_enhanced_code'],
                                                 rcpt['reply_text'],
                                                 smtp_log = rcpt['smtp_log'])
                    ml_stats = mailings_stats.setdefault(recipient.mailing.id, {})
                    if recipient.send_status not in (RECIPIENT_STATUS.FINISHED,
                                                     RECIPIENT_STATUS.ERROR,
                                                     RECIPIENT_STATUS.GENERAL_ERROR,
                                                     RECIPIENT_STATUS.TIMEOUT):
                        recipient.set_send_mail_next_time()
                        if not was_in_softbounce:
                            # recipient.mailing.total_softbounce += 1
                            # recipient.mailing.save()
                            ml_stats['total_softbounce'] = ml_stats.setdefault('total_softbounce', 0) + 1
                    else:
                        # recipient.mailing.total_pending -= 1
                        ml_stats['total_pending'] = ml_stats.setdefault('total_pending', 0) - 1
                        if was_in_softbounce:
                            # recipient.mailing.total_softbounce -= 1
                            ml_stats['total_softbounce'] = ml_stats.setdefault('total_softbounce', 0) - 1
                        if recipient.send_status == RECIPIENT_STATUS.FINISHED:
                            # recipient.mailing.total_sent += 1
                            ml_stats['total_sent'] = ml_stats.setdefault('total_sent', 0) + 1
                            if mailings[recipient.mailing.id].get('backup_customized_emails', False):
                                if not os.path.exists(make_customized_file_name(recipient.mailing.id, str(recipient.id))):
                                    recipient.report_ready = False
                        else:
                            # recipient.mailing.total_error += 1
                            ml_stats['total_error'] = ml_stats.setdefault('total_error', 0) + 1
                        # recipient.mailing.save()

                    recipient.cloud_client = serial
                    recipient.save()
                ids_ok.append(rcpt['_id'])
            except:
                log.exception("Can't update recipient '%s'.", name)

        log.debug("Stored %d reports from satellite [%s] in %.2f s", len(ids_ok), serial, time.time() - t0)
        return ids_ok, mailings_stats

    @staticmethod
    def _update_mailings_stats(result):
        ids_ok, mailings_stats = result
        for mailing_id, ml_stats in mailings_stats.items():
            Mailing.update({'_id': mailing_id}, {'$inc': {
                'total_softbounce': ml_stats.get('total_softbounce', 0),
                'total_sent': ml_stats.get('total_sent', 0),
                'total_error': ml_stats.get('total_error', 0),
                'total_pending': ml_stats.get('total_pending', 0),
                }})
        return ids_ok

    def view_send_reports(self, client, recipients):
        """
        Updates status for finished recipients (in error or not).
        
        Each recipient is described by a dictionary with all its attributes.
        Should returns an array with the IDs of successfully updated recipients.
        """
        self.log.debug("send_reports(...) with %d recipients", len(recipients))


        return deferToThreadPool(reactor, get_reports_threadpool(),
                                 MailingManagerView._store_reports, recipients, self.cloud_client.serial, self.log).\
            addCallback(self._update_mailings_stats)

    def view_send_statistics(self, client, stats_records):
        """
        Updates mailing performances statistics (Read, sent, errors, etc...).
        
        Each statistics record is described by a dictionary with all its attributes.
        Should returns an array with the IDs of successfully updated records.
        """
        from models import MailingHourlyStats

        ids_ok = []
        for stats in stats_records:
            #name = "Unknown"
            try:
                s = MailingHourlyStats.find_one({'sender': self.cloud_client.serial,
                                                 'epoch_hour': stats['epoch_hour']})
                if not s:
                    s = MailingHourlyStats(sender=self.cloud_client.serial,
                                           epoch_hour=stats['epoch_hour'],
                                           date=datetime.utcnow().replace(minute=0, second=0, microsecond=0))
                assert(isinstance(s, MailingHourlyStats))
                s.sent = stats['sent']
                s.failed = stats['failed']
                s.tries = stats['tries']
                #s.read = stats['read']
                #s.unsubscribe = stats['unsubscribe']

                s.save()
                ids_ok.append(str(stats['_id']))

            except:
                self.log.exception("Can't update statistics: %s", repr(stats))
        return ids_ok


class CloudRealm:
    implements(portal.IRealm)

    def __init__(self, max_connections=1):
        self.log = logging.getLogger('cloud_master')
        self.avatars = {}
        self.max_connections = max_connections
        self.__check_for_orphan_recipients = False

    def requestAvatar(self, avatarId, mind, *interfaces):
        global unit_test_mode
        # avatarId is a Cloudclient object from models
        assert(isinstance(avatarId, CloudClient))
        #TODO Add (and update) a lastConnection column to CloudClient table
        if pb.IPerspective not in interfaces: raise NotImplementedError
        if avatarId.serial in self.avatars:
            avatar = self.avatars[avatarId.serial]
        else:
            avatar = self.avatars[avatarId.serial] = ClientAvatar(avatarId)
        if len(avatar.clients) >= self.max_connections:
            raise ValueError("too many connections")
        avatar.attached(mind, avatarId)
        if unit_test_mode:
            avatar.activate_unittest_mode()
        return pb.IPerspective, avatar, lambda a=avatar: a.detached(mind)

    def activate_unittest_mode(self, activated):
        for avatar in self.avatars.values():
            avatar.activate_unittest_mode(activated)

    def close_mailing_on_satellites(self, mailing):
        from models import Mailing
        assert(isinstance(mailing, Mailing))
        for avatar in self.avatars.values():
            self.log.debug("close_mailing_on_satellite(%d, %s)", mailing.id, avatar.cloud_client.serial)
            avatar.close_mailing(mailing)

    def invalidate_mailing_content_on_satellites(self, mailing):
        from models import Mailing
        assert(isinstance(mailing, Mailing))
        for avatar in self.avatars.values():
            avatar.invalidate_mailing_body(mailing)

    def check_recipients_in_clients(self, since_seconds=None):
        """
        Check for 'lost' recipients (recipients marked as handled by a client on master,
        but in reality unknown by the client (may be due to data lost) and remove them
        from the master queue.
        @returns: a Deferred which will be fired when the operation
                  will be finished.
        """
        if self.__check_for_orphan_recipients:
            self.log.debug("Already checking for orphan recipients!")
            return defer.succeed(None)
        self.__check_for_orphan_recipients = True
        from models import MailingRecipient
        l = []
        try:
            if since_seconds is None:
                since_seconds = settings_vars.get_int(settings_vars.ORPHAN_RECIPIENTS_MAX_AGE)
            query = MailingRecipient.find({
                'date_delegated': {
                    '$lt': datetime.utcnow() - timedelta(seconds=since_seconds)},
                'cloud_client': {'$ne': None}
            }, limit=settings_vars.get_int(settings_vars.ORPHAN_RECIPIENTS_MAX_RECIPIENTS))

            def get_recipients_per_client():
                serial = None
                recipients = []
                for recipient in query.sort([('client', pymongo.ASCENDING), ('date_delegated', pymongo.DESCENDING)]):
                    if serial and serial != recipient.cloud_client:
                        yield serial, recipients
                        recipients = []
                    serial = recipient.cloud_client
                    recipients.append(str(recipient['_id']))
                if serial and recipients:
                    yield serial, recipients

            for serial, recipients in get_recipients_per_client():
                self.log.debug("Checking %d orphans from %s", len(recipients), serial)
                if serial in self.avatars and self.avatars[serial].clients:
                    avatar = self.avatars[serial]
                    d = avatar.check_recipients(recipients)
                else:
                    self.log.warn("Found %d recipients handled by disconnected client [%s].", len(recipients), serial)
                    d = defer.succeed({_id: None for _id in recipients})
                d.addCallback(self._check_recipients_cb, serial, recipients)\
                    .addErrback(self._check_recipients_eb, serial)
                l.append(d)
        except Exception, ex:
            self.log.exception("Exception in CloudRealm.check_recipients_in_clients")

        def release_check_flag(result):
            self.__check_for_orphan_recipients = False
            return result

        d = defer.DeferredList(l)
        if not l:
            d = defer.succeed(None)
        d.addBoth(release_check_flag)
        return d

    @defer.inlineCallbacks
    def _check_recipients_cb(self, results, serial, recipient_ids):
        self.log.debug("Queries for handled ids are finished. We can begin the check.")
        assert(isinstance(results, dict))
        unhandled = [ObjectId(id) for id, rcpt in results.items() if not rcpt]
        if unhandled:
            self.log.warn("Found [%d] orphan recipients from client [%s]. Removing them...", len(unhandled), serial)
            yield get_db().mailingrecipient.update_many({'_id': {'$in': unhandled}},
                                                        {'$set': {'in_progress': False}})

        defer.returnValue(unhandled)

    def _check_recipients_eb(self, err, serial):
        self.log.error("Error in check_recipients() for client %s: %s", serial, err)
        return err

    @defer.inlineCallbacks
    def retrieve_customized_content(self):
        db = get_db()

        def _save_customized_content(data_list, file_name):
            if os.path.exists(file_name):
                self.log.warning("Customized file '%s' already exists!", file_name)
            else:
                with file(file_name, 'wt') as f:
                    for data in data_list:
                        f.write(data)
                    f.close()
                self.log.debug("Customized email '%s' written on disk", file_name)
            return file_name

        def _update_recipient(file_name, recipient):
            # recipient.report_ready = True
            # recipient.save()
            return db.mailingrecipient.update_one({'_id': recipient['_id']},
                                                  {'$set': {'report_ready': True, 'modified': datetime.utcnow()}})

        def _handle_failure(err, recipient):
            self.log.error("Error in retrieve_customized_content: %s", err)
            if err.check(exceptions.IOError):
                self.log.error("Can't get customized content for recipient [%s @ %s]",
                               recipient['email'], recipient['mailing'].id)
                return _update_recipient(None, recipient)
            return err

        try:
            dl = []
            # for recipient in MailingRecipient.find({'send_status': RECIPIENT_STATUS.FINISHED, 'report_ready': False},
            #                                        limit=10-self.__content_retrieving):
            recipients = yield db.mailingrecipient.find({'send_status': RECIPIENT_STATUS.FINISHED, 'report_ready': False},
                                                        limit=10)
            for recipient in recipients:
                file_name = os.path.join(settings.CUSTOMIZED_CONTENT_FOLDER, make_customized_file_name(recipient['mailing'].id, str(recipient['_id'])))
                if os.path.exists(file_name):
                    self.log.debug("Customized file '%s' already exists, skipping it...", file_name)
                    dl.append(_update_recipient(file_name, recipient))
                else:
                    avatar = self.avatars[recipient['cloud_client']]
                    dl.append(avatar.retrieve_customized_content(recipient['mailing'].id, str(recipient['_id']))
                              .addCallback(_save_customized_content, file_name)
                              .addCallback(_update_recipient, recipient)
                              .addErrback(_handle_failure, recipient)
                              )
            if dl:
                self.log.debug("retrieve_customized_content() for %d recipients", len(dl))
                yield defer.DeferredList(dl)
        except Exception, ex:
            self.log.exception("Error in retrieve_customized_content()")


class CmCloudCredentialsChecker:
    implements(checkers.ICredentialsChecker)

    credentialInterfaces = (credentials.IUsernamePassword,
                            credentials.IUsernameHashedPassword)

    def _cbPasswordMatch(self, matched, username):
        if matched:
            return username
        else:
            return failure.Failure(cred_error.UnauthorizedLogin())

    def requestAvatarId(self, credentials):
        # avatarId is a CloudClient object from models
        import hmac
        client = CloudClient.search(serial=credentials.username, enabled=True).first()
        if client:
            if credentials.username == settings.SERIAL:
                return client

            return defer.maybeDeferred(
                credentials.checkPassword,
                hmac.HMAC(str(client.shared_key)).hexdigest()
                ).addCallback(
                    self._cbPasswordMatch, client
                )
        else:
            logging.warn("CLOUD MASTER: Unauthorised login for '%s'", credentials.username)
            return defer.fail(cred_error.UnauthorizedLogin())


class MailingPortal(object):

    instance = None

    def __new__(cls): # _new_ is always a class method
        if not MailingPortal.instance:
            MailingPortal.instance = portal.Portal(CloudRealm())
        return MailingPortal.instance

    def __getattr__(self, attr):
        return getattr(self.instance, attr)

    def __setattr__(self, attr, val):
        return setattr(self.instance, attr, val)



def get_cloud_master_factory():
    global mailing_portal
    # First check if local serial is present
    client = CloudClient.search(serial=settings.SERIAL).first()
    if not client:
        from datetime import datetime
        CloudClient.create(serial=settings.SERIAL, enabled=True, paired=False)

    CloudClient.update({}, {'$set': {'paired': False}}, multi=True)
    mailing_portal = MailingPortal()
    mailing_portal.registerChecker(CmCloudCredentialsChecker())
    #pylint: disable-msg=E1101
    #noinspection PyUnresolvedReferences
    factory = pb.PBServerFactory(mailing_portal)
    return factory


