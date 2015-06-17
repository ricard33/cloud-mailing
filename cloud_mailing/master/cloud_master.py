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

import logging
import cPickle as pickle
from datetime import datetime, timedelta
import time
import re
from bson import ObjectId
import pymongo
from zope.interface import implements

from twisted.spread import pb, util
from twisted.internet import reactor, defer
from twisted.application import internet
from twisted.python import failure
from twisted.cred import checkers, portal, error as cred_error, credentials
from twisted.internet.threads import deferToThread, deferToThreadPool
from twisted.python import threadpool

from ..common import settings

from .models import RECIPIENT_STATUS, MAILING_STATUS, MailingTempQueue
from .models import CloudClient, MailingRecipient, Mailing

mailing_portal = None
unit_test_mode = False   # used to make delays shorter

#pylint: disable-msg=W0404

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
        avatarId.date_paired = datetime.now()
        avatarId.save()
        self.clients.append(mind)
        # print "attached to", mind, avatarId

    def detached(self, mind):
        self.cloud_client = CloudClient.grab(self.cloud_client.id)  # reload object
        self.cloud_client.paired = False
        self.cloud_client.date_paired = datetime.now()
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

    def force_check_for_new_recipients(self):
        for c in self.clients:
            c.callRemote("force_check_for_new_recipients")


    def perspective_get_mailing_manager(self):
        # maybe insert here more rights management
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
                util.StringPager(collector, pickle.dumps({'id': mailing_id,
                                                          'header': header,
                                                          'body': body,
                                                          'read_tracking': mailing.read_tracking,
                                                          'click_tracking': mailing.click_tracking,
                                                          'tracking_url': mailing.tracking_url,
                                                          'testing': mailing.testing,
                                                          'delete': False}))
            else:
                self.log.error("Mailing [%d] doesn't exist anymore.", mailing_id)
                util.StringPager(collector, pickle.dumps({'id': mailing_id, 'delete': True}))
        except Exception:
            self.log.exception("Can't get mailing [%d]", mailing_id)
            util.StringPager(collector, pickle.dumps({'id': mailing_id, 'delete': True}))
        #self.log.debug("get_mailing(%d) finished", mailing_id)

    @staticmethod
    def _make_get_recipients_queryset(count, satellite_group, domain_affinity, log):
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
                        #                            print self.cloud_client.serial, "include", domain
                            included.append(domain)
                        else:
                        #                            print self.cloud_client.serial, "exclude", domain
                            excluded.append(domain)
        except Exception:
            log.exception("Error in Affinity format")
        mailing_filter = {
            'status': {'$in': [MAILING_STATUS.FILLING_RECIPIENTS,  # For Test recipients
                               MAILING_STATUS.READY,  # For Test recipients
                               MAILING_STATUS.RUNNING]},
            'satellite_group': satellite_group
        }
        # if satellite_group:
        # mailing_filter['satellite_group'] = satellite_group
        mailing_ids = map(lambda x: x['_id'], Mailing._get_collection().find(mailing_filter, fields=[]))
        query = {
            '$and': [{'$or': [{'in_progress': False}, {'in_progress': {'$exists': False}}]},
                     {'$or': [{'client': False}, {'client': {'$exists': False}}]},
            ],
            'mailing.$id': {'$in': mailing_ids},
        }
        # MailingTempQueue.objects.filter(Q(in_progress=False) | Q(in_progress__isnull=True),
        #                                     client__isnull=True,
        #                                     mailing__status__in=(
        #                                         MAILING_STATUS.FILLING_RECIPIENTS, # For Test recipients
        #                                         MAILING_STATUS.READY, # For Test recipients
        #                                         MAILING_STATUS.RUNNING,
        #                                     ))
        if included and excluded:
            query['$and'].extend([
                {'domain_name': {'$in': included}},
                {'domain_name': {'$nin': excluded}},
            ])
        elif included:
            query['domain_name'] = {'$in': included}
        elif excluded:
            query['domain_name'] = {'$nin': excluded}
        queue = MailingTempQueue.find(query).sort('next_try').limit(count)
        return queue

    def view_get_recipients(self, client, collector, count=1):
        """
        Returns an array of recipients. Each recipient is described by a dictionary with all its attributes.
        """
        # print "view_get_recipients"
        def _send_new_recipients(_count):
            self.log.debug("get_recipients(count=%d)", count)
            t0 = time.time()

            self.cloud_client = CloudClient.grab(self.cloud_client.id)  # reload object
            if not self.cloud_client.enabled:
                self.log.warn("get_recipients() refused for disabled client [%s]", self.cloud_client.serial)
                raise pb.Error("Not allowed!")
            domain_affinity = self.cloud_client.domain_affinity
            satellite_group = self.cloud_client.group
            queue = MailingManagerView._make_get_recipients_queryset(_count, satellite_group, domain_affinity, self.log)

            recipients = []
            for item in queue:
                try:
                    assert(isinstance(item, MailingTempQueue))
                    # mailing = item.mailing
                    # assert(isinstance(mailing, Mailing))
                    rcpt = dict(item.recipient)
                    for key in ('cloud_client', 'in_progress', 'read_time'):
                        rcpt.pop(key, None)
                    rcpt['sender_name'] = item.sender_name
                    rcpt['mail_from'] = item.mail_from
                    rcpt['mailing'] = item['mailing'].id
                    item.client = self.cloud_client
                    item.date_delegated = datetime.utcnow()
                    item.in_progress = True
                    item.save()
                    recipients.append(rcpt)
                except:
                    self.log.exception("Error preparing recipient '%s'...", item.email)

            #noinspection PyUnboundLocalVariable
            # print "results: %d items" % len(result)
            #self.log.debug("get_recipients(%d) finished with %d recipients", _count, len(result))
            return recipients, t0

        def show_time_at_end(t0, rcpts_count, data_len):
            self.log.debug("get_recipients(): Sent %d recipients (%.2f Kb) in %.2f s" % (rcpts_count, data_len / 1024.0, time.time() - t0))

        def send_results(result, _collector, _show_time_at_end):
            recipients, t0 = result
            data = pickle.dumps(recipients)
            util.StringPager(_collector, data, 262144, _show_time_at_end, t0, len(recipients), len(data))

        return deferToThreadPool(reactor, get_new_recipients_threadpool(),
                                 _send_new_recipients, count).addCallback(send_results, collector, show_time_at_end)

    @staticmethod
    def _store_reports(_recipients, serial, log):
        from models import MailingTempQueue, MailingRecipient
        t0 = time.time()

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
                        else:
                            # recipient.mailing.total_error += 1
                            ml_stats['total_error'] = ml_stats.setdefault('total_error', 0) + 1
                        # recipient.mailing.save()

                    recipient.cloud_client = serial
                    recipient.save()
                ids_ok.append(rcpt['_id'])
            except:
                log.exception("Can't update recipient '%s'.", name)
        if ids_ok:
            MailingTempQueue.remove({'recipient._id': {'$in': map(lambda x: ObjectId(x), ids_ok)}})

        log.debug("Stored %d reports from satellite in %.2f s", len(ids_ok), time.time() - t0)
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
        return pb.IPerspective, avatar, lambda a=avatar:a.detached(mind)

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

    def check_recipients_in_clients(self, since_hours=1):
        """
        Check for 'lost' recipients (recipients marked as handled by a client on master,
        but in reality unknown by the client (may be due to data lost) and remove them
        from the master queue.
        @returns: a Deferred which will be fired when the operation
                  will be finished.
        """
        if self.__check_for_orphan_recipients:
            self.log.debug("Already checking for orphan recipients!")
        self.__check_for_orphan_recipients = True
        from models import MailingTempQueue
        d = None
        recipients = []
        serial = None
        try:
            query = MailingTempQueue.find({
                'date_delegated': {
                    '$lt': datetime.utcnow() - timedelta(hours=since_hours)},
                'client': {'$ne': None}
            }, limit=100)
            for item in query.sort([('client', pymongo.ASCENDING), ('date_delegated', pymongo.DESCENDING)]):
                if serial and serial != item.client.serial:
                    break
                serial = item.client.serial
                recipients.append(str(item.recipient['_id']))
            if serial and recipients:
                try:
                    avatar = self.avatars[serial]
                    d = avatar.check_recipients(recipients
                        ).addCallback(self._check_recipients_cb, serial, recipients
                        ).addErrback(self._check_recipients_eb, avatar
                        )
                except KeyError:
                    self.log.warn("Found %d recipients handled by disconnected client [%s].", len(recipients), serial)
        except Exception:
            self.log.exception("Exception in CloudRealm.check_recipients_in_clients")

        def release_check_flag(result):
            self.__check_for_orphan_recipients = False
            return result

        if not d:
            d = defer.succeed(None)
        d.addBoth(release_check_flag)
        return d

    def _check_recipients_cb(self, results, serial, recipient_ids):
        self.log.debug("Queries for handled ids are finished. We can begin the check.")
        assert(isinstance(results, dict))
        unhandled = [id for id, rcpt in results.items() if not rcpt]
        for id in unhandled:
            self.log.warn("Found orphan recipient [%d] handled from client [%s]. Removing it...", id, serial)

        MailingRecipient.update({'_id': {'$in': unhandled}},
                                {'client': None,
                                 'in_progress': False},
                                multi=True)

    def _check_recipients_eb(self, err):
        self.log.error("Error in check_recipients_in_clients: %s", err)
        return err


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


