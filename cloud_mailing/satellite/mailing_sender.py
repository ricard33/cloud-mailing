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
Infrastructure for relaying mail through smart host

Today, internet e-mail has stopped being Peer-to-peer for many problems,
spam (unsolicited bulk mail) among them. Instead, most nodes on the
internet send all e-mail to a single computer, usually the ISP's though
sometimes other schemes, such as SMTP-after-POP, are used. This computer
is supposedly permanently up and traceable, and will do the work of
figuring out MXs and connecting to them. This kind of configuration
is usually termed "smart host", since the host we are connecting to
is "smart" (and will find MXs and connect to them) rather then just
accepting mail for a small set of domains.

The classes here are meant to facilitate support for such a configuration
for the twisted.mail SMTP server
"""
import os
import time
import logging
import cPickle as pickle
import threading
from bson import DBRef, ObjectId
from datetime import datetime
from datetime import timedelta

from twisted.python.failure import Failure
from twisted.internet import error #import DNSLookupError, TimeoutError, ConnectionLost, ConnectionRefusedError, ConnectError
from twisted.mail import smtp
from twisted.application import internet
from twisted.internet import defer
from twisted.internet.threads import deferToThread
from twisted.internet import reactor
from twisted.spread import pb
from twisted.spread.util import CallbackPageCollector

from .mx import MXCalculator, FakedMXCalculator
from sendmail import SMTPRelayerFactory
from ..common import settings
from ..common.config_file import ConfigFile
import settings_vars
from .mail_customizer import MailCustomizer
from models import Mailing, MailingRecipient, RECIPIENT_STATUS, HourlyStats, DomainStats, DomainConfiguration, \
    ActiveQueue


class EmtpyFactory(Exception):
    pass


def getAllPages(referenceable, methodName, *args, **kw):
    """
    A utility method that will call a remote method which expects a
    PageCollector as the first argument.
    
    This version is an improved one from twisted, with an errback called in case of error.
    """
    d = defer.Deferred()
    referenceable.callRemote(methodName, CallbackPageCollector(d.callback), *args, **kw).addErrback(d.errback)
    return d


class MailingSender(pb.Referenceable):
    """The CM mailing queue.

    Manage mailing relayers, keeping track of the existing connections,
    each connection's responsibility in term of messages. Create
    more relayers if the need arises.

    Someone should press .checkState periodically
    """

    def __init__(self, cloud_client, timer_delay = 5, delay_if_empty = 20, maxConnections = 2):
        """
        @type maxConnections: C{int}
        @param maxConnections: The maximum number of SMTP connections to
        allow to be opened at any given time.

        Default values are meant for a small box with 1-5 users.
        """
        self.cloud_client = cloud_client
        self.timer_delay = timer_delay
        self.delay_if_empty = delay_if_empty
        self.mailing_manager = None
        self.timer = None
        self.log = logging.getLogger('ml_queue')

        self.maxConnections = maxConnections
        self.maxMessagesPerConnection = 100
        self.relay_manager = ActiveQueuesList(self.log)
        self.nextTime = 0
        self.handlingQueueLock = threading.Lock()
        self.handling_check_for_new_recipients = False
        self.handling_get_mailing = False  # no need for locker as it is in same thread
        self.handling_get_mailing_next_time = 0
        self.handling_finished_recipients = False  # no need for locker as it is in same thread
        if settings.TEST_FAKE_DNS:
            Queue.mxcalc = FakedMXCalculator()
        else:
            Queue.mxcalc = MXCalculator()

        self.is_connected = False
        self.invalidate_all_mailing_content()
        self.delete_all_customized_temp_files()
        self.clear_all_send_mail_in_progress()

    def disconnected(self, remoteRef):
        self.log.warn("MailingManager disconnected!! %s", remoteRef)
        self.mailing_manager = None

    def remote_is_ready(self):
        return True
    
    def remote_add_recipient(self, arg):
        print "add_recipient() called with", arg
        
    def cb_get_mailing_manager(self, mailing_manager):
        self.mailing_manager = mailing_manager
        self.mailing_manager .notifyOnDisconnect(self.disconnected)
        if not self.timer:
            self.timer = internet.TimerService(self.timer_delay, self.check_mailing)
            self.timer.startService()
            t = internet.TimerService(3600, self.remove_closed_mailings)
            t.startService()
            internet.TimerService(60, self.relay_manager.check_for_zombie_queues).startService()

    def check_for_new_recipients(self):
        self.log.debug("check_for_new_recipients()")
        t0 = time.time()
        if not self.mailing_manager:
            self.log.info("MailingManager not connected (NULL). Can't get new recipients. Waiting...")
            self.handling_check_for_new_recipients = False  # HACK Avoid a bug: lock is not always released on connection lost
            return
        if self.handling_check_for_new_recipients:
            self.log.debug("check_for_new_recipients() is locked...")
            # already processing
            return
        self.handling_check_for_new_recipients = True
        try:
            max_recipients = min(settings_vars.get_int(settings_vars.MAILING_MAX_NEW_RECIPIENTS), 1000)
            # d = self.mailing_manager.callRemote('get_recipients', max_recipients)
            d = getAllPages(self.mailing_manager, 'get_recipients', max_recipients)
            d.addCallbacks(self.cb_get_recipients, self.eb_get_recipients, callbackArgs=[t0])
            self.is_connected = True
        except pb.DeadReferenceError:
            self.log.info( "MailingManager not connected. Can't get new recipients. Waiting..." )
            self.is_connected = False
            self.handling_check_for_new_recipients = False
        except Exception:
            self.log.exception("Unknown exception in check_for_new_recipients()")
            self.handling_check_for_new_recipients = False

    def cb_get_recipients(self, data_list, t0):
        try:
            recipients = pickle.loads(''.join(data_list))
            self.log.debug("Received %d new recipients from Manager in %.1fs.", len(recipients), time.time() - t0)
            self.handling_check_for_new_recipients = False
            c = 0
            for r in recipients:
                # self.log.debug("Recipient: %s", r)
                mailing = Mailing.grab(r['mailing'])
                if not mailing:
                    mailing = Mailing.create(_id=r['mailing'])
                try:
                    MailingRecipient.create(mailing=DBRef("mailing", mailing.id),
                                            _id=r['_id'],
                                            tracking_id=r['tracking_id'],
                                            contact_data=r.get('contact'),
                                            email=r['email'],
                                            mail_from=r['mail_from'],
                                            sender_name=r.get('sender_name'),
                                            domain_name=r['email'].split('@', 1)[1],
                                            first_try=r.get('first_try'),
                                            next_try=r['next_try'],
                                            try_count=r.get('try_count'),
                    )
                    c += 1
                    #print r['id'], '-->', r['recipient']
                except Exception, ex:
                    print ex
                    self.log.warn("Recipient '%s' was ignored due to Exception: %s", r['email'], ex)
                    # should we inform the master ? it may be not necessary because it means that it is currently already handled
                    # and so, an update will be sent soon or late.
            if c:
                self.log.debug("Recipients added to local queue.")
            self.nextTime = 0
        except pickle.PickleError:
            self.log.exception("Can't decode recipients data")
        except Exception:
            self.log.exception("Unexpected error getting recipients data")
        return None

    def eb_get_recipients(self, err):
        self.handling_check_for_new_recipients = False
        err_msg = str(err.value) or str(err)
        self.log.error("Error getting new recipients: %s", err_msg)
        
    def check_for_missing_mailing(self):
        """Check in mailing table for missing headers and bodies, then
        ask them to the master.
        """
        if not self.mailing_manager:
            self.log.info( "MailingManager not connected (NULL). Can't get mailing bodies. Waiting..." )
            return
        if self.handling_get_mailing:
            # already processing
            return
        if time.time() < self.handling_get_mailing_next_time:
            return
        self.handling_get_mailing = True
        mailing = Mailing.find({'$or': [{'header': None}, {'body_downloaded': False}], 'deleted': False}).first()
        if not mailing:
            self.handling_get_mailing = False
            self.handling_get_mailing_next_time = time.time() + self.delay_if_empty
            #print "check_for_missing_mailing: Waiting for %d seconds..." % self.delay_if_empty
            return
            
        try:
#            d = self.mailing_manager.callRemote('get_mailing', mailing.id)
            d = getAllPages(self.mailing_manager, "get_mailing", mailing.id)
            d.addCallbacks(self.cb_get_mailing, self.eb_get_mailing)
            self.is_connected = True
        except pb.DeadReferenceError:
            self.log.info( "MailingManager not connected. Can't get mailing bodies. Waiting..." )
            self.is_connected = False
            self.handling_get_mailing = False
            
    def cb_get_mailing(self, data_list):
        data = ''.join(data_list)
        self.handling_get_mailing = False
        mailing_id = None
        #noinspection PyBroadException
        try:
            mailing_dict = pickle.loads(data)
            mailing_id = mailing_dict['id']
            if mailing_id in MailCustomizer.mailingsContent:
                del MailCustomizer.mailingsContent[mailing_id]

            if not mailing_dict.get('delete', False):
                header = mailing_dict['header']
                body = mailing_dict['body']
                tracking_url = mailing_dict['tracking_url']
                self.log.debug("Received header and body for mailing [%d] from Manager", mailing_id)
                mailing = Mailing.grab(mailing_id)
                if mailing:
                    mailing.header = header
                    mailing.body = body
                    mailing.body_downloaded = True
                    mailing.testing = mailing_dict.get('testing', False)
                    mailing.backup_customized_emails = mailing_dict.get('backup_customized_emails', False)
                    mailing.read_tracking = mailing_dict.get('read_tracking', True)
                    mailing.click_tracking = mailing_dict.get('click_tracking', False)
                    mailing.tracking_url = tracking_url
                    mailing.save()
                else:
                    self.log.error("Mailing [%d] doesn't exist. Can't update header and body data.", mailing_id)
            else:
                self.log.warn("Received DELETE order for mailing [%d] from Manager", mailing_id)
                mailing = Mailing.grab(mailing_id)
                if mailing:
                    mailing.delete()

        except pickle.PickleError:
            self.log.exception("Can't decode mailing data")
        except Exception:
            self.log.exception("Unexpected error getting mailing data")
        return None
        
    def eb_get_mailing(self, err):
        self.handling_get_mailing = False
        err_msg = str(err.value) or str(err)
        self.log.error("Error getting mailing data: %s", err_msg)
        
    def send_report_for_finished_recipients(self, finished_recipients):
        """
        Send status report for finished recipients to the master. 
        
        Args:
            finished_recipients:  a query_set to these recipients.
            
        """
        if not self.mailing_manager:
            self.log.info( "MailingManager not connected (NULL). Can't send reports. Waiting..." )
            return
        self.handling_finished_recipients = True
        try:
            list_of_deferred = []
            rcpts = []
            max_reports = min(settings_vars.get_int(settings_vars.MAILING_MAX_REPORTS), 5000)
            for recipient in finished_recipients[0:max_reports]:
                rcpt = dict(recipient)
                for field in ('contact_data', 'unsubscribe_id'):
                    rcpt.pop(field, None)
                rcpt['_id'] = str(recipient['_id'])
                rcpt['mailing'] = recipient['mailing'].id
                rcpts.append(rcpt)
            if rcpts:
                self.log.debug("Sending reports for %d recipients", len(rcpts))
                d1 = self.mailing_manager.callRemote('send_reports', rcpts)
                d1.addCallbacks(self.cb_send_reports, self.eb_send_reports)
                list_of_deferred.append(d1)

            stats = []
            for stat in HourlyStats.search(up_to_date=False):
                s = dict(stat)
                s.pop('up_to_date',None)
                stats.append(s)
            if stats:
                d2 = self.mailing_manager.callRemote('send_statistics', stats)
                d2.addCallbacks(self.cb_send_statistics, self.eb_send_statistics)
                list_of_deferred.append(d2)
            
            if list_of_deferred:
                d = defer.DeferredList(list_of_deferred)
                d.addCallback(self.cb_end_handling_finished_recipients)
            else:
                self.handling_finished_recipients = False

            self.is_connected = True
        except pb.DeadReferenceError:
            self.log.info("MailingManager not connected. Waiting...")
            self.is_connected = False
            self.handling_finished_recipients = False
        except Exception:
            self.log.exception("Error in send_report_for_finished_recipients()")
            self.handling_finished_recipients = False

    def cb_send_reports(self, recipient_ids):
        try:
            MailingRecipient.remove({'_id': {'$in': map(lambda id: ObjectId(id), recipient_ids)}})
        except Exception:
            self.log.exception("Error while removing finished recipients.")
        
    def eb_send_reports(self, err):
        err_msg = str(err.value) or str(err)
        self.log.error("Error while reporting finished recipients: %s", err_msg)
        
    def cb_send_statistics(self, stats_ids):
        # BUG possible loose of statistics if row updated since it was sent to master
        try:
            HourlyStats.update({'_id': {'$in': stats_ids}}, {'$set': {'up_to_date': True}}, multi=True)
        except Exception, ex:
            self.log.exception("Error while removing updated statistics for ids [%s].", stats_ids)
        
    def eb_send_statistics(self, err):
        err_msg = str(err.value) or str(err)
        self.log.error("Error while reporting finished recipients: %s", err_msg)
        
    def cb_end_handling_finished_recipients(self, dummy):
        self.handling_finished_recipients = False
            
    # KEEP ?
    def forceToCheck(self):
        self.nextTime = 0

    @staticmethod
    def make_queue_filter():
        mailing_ids = map(lambda x: x['_id'],
                          Mailing._get_collection().find({'body_downloaded': True}, fields=('_id',)))
        queue_filter = {'$or': [{'in_progress': False}, {'in_progress': None}],
                        'finished': False,
                        'mailing.$id': {'$in': mailing_ids}}
        return queue_filter

    def check_mailing(self):
        """
        Synchronize with the state of the world, and maybe launch a new
        relay.

        Call me periodically to check I am still up to date.

        @return: None or a Deferred which fires when all of the SMTP clients
        started by this call have disconnected.
        """
        need_to_release = False

        if time.time() < self.nextTime:
            return
        try:
            delay_for_next_time = self.delay_if_empty  # default delay
            if not self.handlingQueueLock.acquire(False):
                return
            need_to_release = True
            
            self.maxConnections = settings_vars.get_int(settings_vars.MAILING_QUEUE_MAX_THREAD)
            #mailing_queue_max_size = settings_vars.get_int(settings_vars.MAILING_QUEUE_MAX_SIZE)
            mailing_queue_min_size = settings_vars.get_int(settings_vars.MAILING_QUEUE_MIN_SIZE)
            self.maxMessagesPerConnection = settings_vars.get_int(settings_vars.MAILING_QUEUE_MAX_THREAD_SIZE)
            
            in_progress = MailingRecipient.search(in_progress=True).count()
            temp_queue_count = MailingRecipient.search(finished=False).count()
            to_report_count = MailingRecipient.search(finished=True).count()
            active_relay_count = self.relay_manager.activeRelayCount()

            self.log.debug("Number of active relays: %d / Max relays count: %d / Max recipients per relay: %d / "
                           "In progress = %d / Queue size = %d / ReportsQueue % d",
                           active_relay_count, self.maxConnections, self.maxMessagesPerConnection, in_progress,
                           temp_queue_count, to_report_count)

            if temp_queue_count < mailing_queue_min_size:
                self.check_for_new_recipients()

            self.check_for_missing_mailing()
    
            if not self.handling_finished_recipients:
                finished = MailingRecipient.search(in_progress=False, finished=True)
                outdated_stats = HourlyStats.search(up_to_date=False)
                if finished.first() or outdated_stats.first():
                    self.send_report_for_finished_recipients(finished.clone())
                    delay_for_next_time = 0

            if active_relay_count >= (int(self.maxConnections / 2) or 1):
                # this is to limit the number of database queries. Assuming that there is a sufficient
                # number of recipients to handle, we don't get new ones.
                self.log.debug("Skipping filling queue due to too much concurrent connections (%d)", active_relay_count)
                return

            queue_filter = self.make_queue_filter()
            if MailingRecipient.find(queue_filter).first():
                need_to_release = False
                deferToThread(self.handle_mailing_queue, 
                              queue_filter
                              )
                delay_for_next_time = 0
            self.nextTime = time.time() + delay_for_next_time

        except Exception:
            self.log.exception("Unknown exception in check_mailing.")
        finally:
            if need_to_release:
                self.handlingQueueLock.release()

    def handle_mailing_queue(self, queue_filter):
        #noinspection PyBroadException
        try:
            self.log.debug('handle_mailing_queue()')
            t0 = time.time()

            # Relay configuration
            config = ConfigFile()
            config.read(settings.CONFIG_FILE)

            mail_server = {'mode': config.get('SEND_MAIL', 'method', 'direct'),
                           'auth_needed': config.getboolean('SEND_MAIL_PROVIDER', 'authenticate', False),
                           'url': config.get('SEND_MAIL_PROVIDER', 'server_name', ''),
                           'port': config.getint('SEND_MAIL_PROVIDER', 'server_port', 25),
                           'login': config.get('SEND_MAIL_PROVIDER', 'login', ''),
                           'password': config.get('SEND_MAIL_PROVIDER', 'password', ''),
                           }

            Queue.mxcalc.cleanupBadMXs()

            testing_mailings = map(lambda x: x['_id'], Mailing._get_collection().find({'testing': True}, fields=('_id',)))
            testing_queue_filter = queue_filter.copy()
            queue_filter.setdefault('$and', []).append({'mailing.$id': {'$nin': testing_mailings}})
            testing_queue_filter.setdefault('$and', []).append({'mailing.$id': {'$in': testing_mailings}})

            exchanges = self._get_exchanges_dict(dict(queue_filter))
            test_exchanges = self._get_exchanges_dict(dict(testing_queue_filter))

            if not exchanges and not test_exchanges:
                # self.nextTime = time.time() + 60
                return

            if exchanges:
                self._make_relayers(exchanges, mail_server, testing=False)
            if test_exchanges:
                self._make_relayers(test_exchanges, mail_server, testing=True)

        except KeyboardInterrupt:
            self.log.info('Mailing queue stopped by user (Crtl-C)')
            raise
        except Exception:
            self.log.exception("runMailingQueue")
        finally:
            self.log.debug("handle_mailing_queue() finished in %.1fs", time.time() - t0)
            self.handlingQueueLock.release()
            
    def _get_exchanges_dict(self, queue_filter):
        active_queues_count = self.relay_manager.activeRelayCount()
        exchanges = {} # dict (Key: domain name; Value: list of recipients)
        skip_domains = []
        # TODO load domain config then list domain that has reach their max queues number to filter them from query
        for recipient in MailingRecipient.find(queue_filter).sort('next_try'):
            assert(isinstance(recipient, MailingRecipient))
            to = recipient.email
            parts = to.split('@', 1)
            if len(parts) != 2:
                self.log.error("Illegal message destination: " + to)
                continue
            domain = parts[1]
            if domain in skip_domains:
                continue

            domain_config = DomainConfiguration.search(domain_name=domain).first() or {}

            if domain not in exchanges:
                if len(exchanges) >= (self.maxConnections - active_queues_count):
                    skip_domains.append(domain)
                    continue # skip this domain
                if ActiveQueue.search(domain_name=domain).count() >= domain_config.get('max_relayers', settings_vars.get(settings_vars.DEFAULT_MAX_QUEUE_PER_DOMAIN)):
                    # No more queue for this domain
                    skip_domains.append(domain)
                    continue
                exchanges[domain] = []
            if len(exchanges[domain]) >= self.maxMessagesPerConnection:
                skip_domains.append(domain)
                continue # skip this recipient
            exchanges[domain].append(recipient)
            recipient.set_send_mail_in_progress()
        return exchanges

    def _make_relayers(self, exchanges, mail_server, testing=False):
        for (domain, recipients) in exchanges.iteritems():
            q_manager = Queue(domain, recipients, mail_server, testing)
            queue_id = self.relay_manager.add_queue(q_manager)
            self.log.debug("Relayer for '%s' created." % domain)
            d = q_manager.start()

            d.addCallbacks(self._cbRelayer, self._ebRelayer,
                           callbackArgs=(queue_id,),
                           errbackArgs=(domain, queue_id,))


    def _cbRelayer(self, domainName, queue_id):
        self.log.debug("Relayer for '%s' finished." % domainName)
        self.relay_manager.removeActiveRelay(queue_id)

    def _ebRelayer(self, err, domain, queue_id):
        # if err.check(dns.exception.DNSException):
        #     err_msg = str(err.value.__doc__)
        # else:
        err_msg = (str(err.value) or str(err)).decode('utf-8', 'ignore')
        self.log.error("Relayer '%s' finished with error '%s'.", domain, err_msg)
        recipients = self.relay_manager.getActiveRelayRecipients(queue_id)
        if recipients:
            try:
                #for recipient in recipients:
                #    if recipient.in_progress:
                #        email_from = recipient.mail_from
                #        email_to   = recipient.email
                #        handle_recipient_failure(err, recipient, email_from, email_to, self.log)
                pass
            finally:
                # by security, to be certain to not block our mailing queue
                self.relay_manager.removeActiveRelay(queue_id)

    def invalidate_all_mailing_content(self):
        self.log.debug("Invalidating all mailing content...")
        Mailing.update({}, {'$set': {'body_downloaded': False, 'header': None, 'body': None}}, multi=True)

    def clear_all_send_mail_in_progress(self):
        self.log.debug("Reseting all mailing recipients in progress...")
        MailingRecipient.update({'$or': [{'send_status': RECIPIENT_STATUS.IN_PROGRESS}, {'in_progress': True}]},
                                {'$set': {'send_status': RECIPIENT_STATUS.READY, 'in_progress': False}},
                                multi=True)

    def close_mailing(self, queue_id):
        """Delete from db all recipients from a mailing and remove all customized files
           from temp folder."""
        self.log.info("Closing mailing id %d", queue_id)
        mailing = Mailing.grab(queue_id)
        if mailing:
            mailing.deleted = True
            mailing.save()
            # noinspection PyCallByClass
            MailingRecipient.remove({'mailing.$id': mailing.id, 'in_progress': False, 'finished': False})
        else:
            self.log.warn("Mailing id [%d] doesn't exist!", queue_id)
            
        if queue_id in MailCustomizer.mailingsContent:
            del MailCustomizer.mailingsContent[queue_id]

        self.log.debug("Delete all customized files for mailing [%d].", queue_id)
        import glob
        for entry in glob.glob(os.path.join(settings.MAIL_TEMP, MailCustomizer.make_patten_for_queue(queue_id))):
            #noinspection PyBroadException
            try:
                os.remove(entry)
            #pylint: disable-msg=W0703
            except Exception:
                self.log.exception("Can't remove customized file '%s'", entry)

    def remove_closed_mailings(self):
        self.log.info("Remove closed mailings")
        for mailing in Mailing.search(deleted=True):
            MailingRecipient.remove({'mailing.$id': mailing.id, 'in_progress': False, 'finished': False})
            if not MailingRecipient.find({'mailing.$id': mailing.id}).first():
                self.log.info("No more recipients for closed mailing [%d]. Deleted...", mailing.id)
                mailing.delete()
            else:
                self.log.warn("Some recipients are still present for closed mailing [%d].", mailing.id)


    def delete_all_customized_temp_files(self):
        """Delete all customized files from temp folder."""
        self.log.debug("Delete all customized files from temp folder.")
        import glob
        for entry in glob.glob(os.path.join(settings.MAIL_TEMP, "cust_ml_*.rfc822")):
            #noinspection PyBroadException
            try:
                os.remove(entry)
            #pylint: disable-msg=W0703
            except Exception:
                self.log.exception("Can't remove customized file '%s'", entry)


class ActiveQueuesList(object):
    """Class to handle active relays and provide a way to share live information about relay via DB storage"""
    def __init__(self, logger):
        self.log = logger
        self.managed = {}  # SMTP clients we're managing (key = ObjectId, value = Queue)
        ActiveQueue.remove({})

    def add_queue(self, queue):
        """
        Add a queue into the active queues list then return its id.
        """
        active_queue = ActiveQueue.create(domain_name=queue.domain, recipients=queue.recipients)
        self.managed[active_queue.id] = queue
        return active_queue.id

    def activeRelayCount(self):
        """Returns the active queues count."""
        return len(self.managed)

    def removeActiveRelay(self, queue_id):
        def _remove(queue_id):
            ActiveQueue.remove({'_id': queue_id})
            del self.managed[queue_id]

        delay = settings_vars.get_float(settings_vars.MAILING_QUEUE_ENDING_DELAY)
        if delay > 0:
            reactor.callLater(delay, _remove, queue_id)
        else:
            _remove(queue_id)

    # # Not used
    # def removeAllActiveRelays(self):
    #     self.managed = {}
    #
    # # Not used
    # def getActiveRelays(self):
    #     return self.managed.keys()
    #
    # # Not used
    # def getActiveRelaysInfo(self):
    #     return [{'domain': factory.targetDomain, 'startDate': factory.startDate} for factory in self.managed.keys()]

    def getActiveRelayRecipients(self, queue_id):
        """Returns the recipients list for the specified queue_id, or None if queue is not found."""
        queue = self.managed.get(queue_id, None)
        if queue:
            return queue.recipients
        return None

    def check_for_zombie_queues(self):
        self.log.debug("Check for zombie queues")
        max_age = settings_vars.get_int(settings_vars.ZOMBIE_QUEUE_AGE_IN_SECONDS)
        ids = [queue.id for queue in ActiveQueue.find({'created': {'$lt': datetime.utcnow() - timedelta(seconds=max_age)}})]
        if ids:
            self.log.warn("Found %d zombie queues (older than %d seconds)", len(ids), max_age)
            for _id in ids:
                queue = self.managed[_id]
                self.log.warn("Deleting queue for '%d' that contains %d recipients", queue.domain, len(queue.recipients))
                queue._ebExchange(defer.failure.Failure(defer.TimeoutError), queue.factory, queue.domain, queue.recipients)
                self.removeActiveRelay(_id)


class Queue(object):
    """
    Handle a single queue (one connection to one smtp server).

    A queue is a resource limiter/controller. A queue should only have one customizer thread, and one TCP connection.
    Also, a queue can only have MAILING_QUEUE_MAX_THREAD_SIZE recipients. So the memory usage is limited too.
    """
    PORT = 25
    mx_in_use = [] # IP addresses of MX server where we are currently connected
    mxcalc = None

    def __init__(self, domain, recipients, mail_server, testing=False):
        self.domain = domain
        self.recipients = recipients
        self.mail_server = mail_server
        self.testing = testing
        self.log = logging.getLogger('ml_queue.%s' % domain)
        self.fake_target_ip = settings.TEST_TARGET_IP
        self.fake_target_port = settings.TEST_TARGET_PORT
        self.factory = None
        self.t0_customization = 0

    def start(self):
        """
        Start the queue handling with all its steps (MX resolution, emails customization, connection to target server,
        sending emails.
        @return:
        """
        kw = {}
        if self.mail_server['mode'] in ('provider', 'smarthost') and self.mail_server['auth_needed']:
            kw['username'] = self.mail_server['login']
            kw['secret'] = self.mail_server['password']
        main_domain = settings_vars.get(settings_vars.EHLO_STRING)
        self.factory = SMTPRelayerFactory(self.domain, retries=0,
                                          connectionClosedCallback=self._cbConnectionClosed,
                                          connectionFailureErrback=self._ebConnectionFailure,
                                          **kw)
        self.factory.domain = str(main_domain or smtp.DNSNAME)

        self.log.debug("Requesting MX servers for relayer '%s'...", self.domain)

        if self.mail_server['mode'] in ('provider', 'smarthost'):
            mxs = [ self.mail_server['url'] ]
            self.PORT = self.mail_server['port']
            d = defer.succeed(mxs)
        else:
            d = self.mxcalc.getMX(self.domain)
            d.addCallback(self._cb_store_mx_list)

        d.addCallback(lambda mxs: deferToThread(self._customize_recipients, mxs, self.factory, self.recipients))
        d.addCallback(self._send_all_emails, self.PORT, self.factory, self.testing)

        d.addErrback(self._ebExchange, self.factory, self.domain, self.recipients)

        return d

    def _cb_store_mx_list(self, mxs):
        self.log.debug("MX list for '%s': %s", self.domain, repr(mxs))
        return map(lambda mx: str(mx.name), mxs)

    def _cbConnectionClosed(self, connector):
        """Callback called by SMTPRelayerFactory for connection closed normally.
        Allows to remove this host from used list.
        """
        ip = connector.getDestination().host
        self.mx_in_use.remove(ip)

    def _ebConnectionFailure(self, connector, err):
        """Callback called by SMTPRelayerFactory for connection error.
        Allows to temporary disable this host.
        """
        ip = connector.getDestination().host
        self.mxcalc.markBad(ip)
        self.mx_in_use.remove(ip)

    def _customize_recipients(self, mxs, factory, recipients):
        self.log.debug("Starting customization...")
        self.t0_customization = time.time()
        for recipient in recipients:
            if not recipient.mailing:
                self.log.warn("Can't find mailing [%d] for recipient [%s:%s]",
                              recipient['mailing'], recipient.id, recipient.email)
                continue
            rcpt_manager = RecipientManager(factory, recipient, self.log)
            rcpt_manager.send().addCallbacks(self._cbRecipient,
                                             self._ebRecipient,
                                             callbackArgs=(factory,),
                                             errbackArgs=(recipient, factory,)
                                             )
        if factory.get_recipients_count():
            return mxs
        else:
            self.log.error("Factory is empty! All recipients failed at customization level.")
            return Failure(EmtpyFactory("No recipients for domain '%s'!" % self.domain))

    def _send_all_emails(self, addresses, port, factory, testing):
        self.log.debug("Customization finished in %.1fs", time.time() - self.t0_customization)
        # print "_send_all_emails(%s): %s" % (factory.targetDomain, addresses)
        DomainStats.add_dns_success(factory.targetDomain)

        self.log.debug("Factory [%s] contains '%d' recipients", factory.targetDomain, factory.get_recipients_count())
        if testing:
            address = self.fake_target_ip
            port = self.fake_target_port
        else:
            address = addresses[0]
        reactor.connectTCP(address, port, factory)
        #noinspection PyTypeChecker
        self.mx_in_use.append(address)
        #pylint: enable-msg=E1101

        return factory.deferred

    def _ebExchange(self, err, factory, domain, recipients):
        self.log.error('Error setting up managed relay factory for %s: %s', domain, repr(err))
        try:
            from twisted.names.error import DNSServerError, DNSQueryRefusedError, DNSNameError, DNSQueryTimeoutError, \
                DomainError, AuthoritativeDomainError

            domain_in_error = DomainStats.search_or_create(domain_name=domain)
            fatal_errors_count = domain_in_error.dns_fatal_errors # keep the value before changing it with 'F()' function

            if err.check(DNSServerError):
                err_msg = "DNS error! Maybe a bad defined domain."
                DomainStats.add_dns_fatal_error(domain, err.value)
                fatal_errors_count += 1

            elif err.check(error.DNSLookupError, AuthoritativeDomainError):
                err_msg = "DNS lookup failed! This domain name doesn't exist."
                DomainStats.add_dns_fatal_error(domain, err.value)
                fatal_errors_count += 1

            elif err.check(DNSQueryRefusedError):
                err_msg = "DNS query refused! Maybe a network problem."
                DomainStats.add_dns_temp_error(domain, err.value)

            elif err.check(defer.TimeoutError, DNSQueryTimeoutError):
                err_msg = "DNS Timeout! Can't get answer in a reasonable time."
                DomainStats.add_dns_temp_error(domain, err.value)

            elif err.check(AttributeError):
                err_msg = "Unknown error (was AttributeError). We will try later."
                DomainStats.add_dns_temp_error(domain, err.value)
                import traceback
                self.log.error("Attribute error: %s\n%s", err.value, ''.join(traceback.format_exception(type(err.value), err.value, err.getTracebackObject())))

            else:
                from twisted.names.dns import Message
                if err.value and isinstance(err.value, DomainError):
                    if isinstance(err.value.message, basestring):
                        err_msg = err.value.message
                    else:
                        err_msg = str(err.value.__name__)
                else:
                    err_msg = str(err.value) or str(err)
                DomainStats.add_dns_fatal_error(domain, err.value)
                fatal_errors_count += 1

            self.log.error(err_msg)

            for recipient in recipients:
                # TODO use handle_recipient_failure()
                if recipient.in_progress:    # here should be always true
                    if fatal_errors_count < 5:
                        recipient.update_send_status(RECIPIENT_STATUS.WARNING, smtp_message = err_msg)
                        HourlyStats.add_try()
                        recipient.set_send_mail_next_time()
                        self.log.debug("Mailing [%d]: from <%s> recipient <%s> postponed to %s" % (recipient.mailing.id,
                                                                                                   recipient.mail_from,
                                                                                         recipient,
                                                                                         recipient.next_try.isoformat(' ')))
                    else:
                        self.log.error("Max errors count reach for domain '%s', rejecting recipient '%s'", domain, recipient)
                        print fatal_errors_count
                        recipient.update_send_status(RECIPIENT_STATUS.ERROR, smtp_message = err_msg)
                        recipient.mark_as_finished()
                        HourlyStats.add_failed()
            return err

        except Exception:
            self.log.exception("Exception handling errors in Queue")
            raise

    def _cbRecipient(self, recipient, factory):
        #self.log.debug("Recipient '%s' finished with success." % recipient)
        pass

    def _ebRecipient(self, err, recipient, factory):
        #self.log.error("Recipient '%s' finished with error '%s'." % (recipient, err))
        pass


class RecipientManager(object):
    def __init__(self, factory, recipient, log):
        assert(isinstance(recipient, MailingRecipient))
        self.factory = factory
        self.recipient = recipient
        self.deferred = defer.Deferred()
        #self.customizerDeferred = defer.Deferred()
        self.log = log
        self.email_from = recipient.mail_from
        self.email_to   = recipient.email
        self.temp_filename = None
        
    def send(self):
        try:
            uid, path = MailCustomizer(self.recipient, True,
                                       self.recipient.mailing.read_tracking,
                                       self.recipient.mailing.click_tracking).customize()
            self.temp_filename = path
            self.factory.send_email(self.email_from, (self.email_to,), file(path, 'rt'))\
                .addCallbacks(self.onSuccess, self.onFailure)

        except OSError, ex:
            self.log.error("Mailing customizer failure for mailing %s and recipient %s: %s", self.email_from, self.email_to, str(ex))
            if ex.errno == 2:  # No such file or directory
                self.recipient.update_send_status(RECIPIENT_STATUS.WARNING, smtp_message = "Email customization temporary error: %s" % str(ex.message))
            else:
                self.recipient.update_send_status(RECIPIENT_STATUS.GENERAL_ERROR, smtp_message = str(ex))

        except smtp.AddressError, ex:
            self.log.error("[Mailing %s] Failed to add email '%s' to SMTPRelayerFactory: %s", self.email_from, self.email_to, ex.message)
            self.recipient.update_send_status(RECIPIENT_STATUS.GENERAL_ERROR, smtp_message = ex.message)
            self.recipient.mark_as_finished()
            HourlyStats.add_failed()
            DomainStats.add_failed(self.factory.targetDomain)
            self.deferred.errback(Failure(ex))

        except Exception, ex:
            self.log.exception("[Mailing %s] Failed to handle email '%s'", self.email_from, self.email_to)
            self.recipient.update_send_status(RECIPIENT_STATUS.GENERAL_ERROR, smtp_message = str(ex))
            self.recipient.mark_as_finished()
            HourlyStats.add_failed()
            DomainStats.add_failed(self.factory.targetDomain)
            self.deferred.errback(Failure(ex))

        return self.deferred

    def onSuccess(self, data):
        logging.getLogger('mailing.out').info("MAILING [%d] SENT FROM <%s> TO <%s>", self.recipient.mailing.id,
                                              self.email_from, self.email_to)
        self.recipient.update_send_status(RECIPIENT_STATUS.FINISHED, smtp_message = '')
        self.recipient.mark_as_finished()
        HourlyStats.add_sent()
        DomainStats.add_sent(self.factory.targetDomain)
        print Mailing._get_collection().find({'_id': self.recipient.mailing.id}, {'backup_customized_emails': True})[0]
        if self.temp_filename and os.path.exists(self.temp_filename):
            if Mailing._get_collection().find({'_id': self.recipient.mailing.id}, {'backup_customized_emails': True})[0].get('backup_customized_emails', False):
                self.log.debug("Moving customized content '%s' to '%s' folder", os.path.basename(self.temp_filename), settings.CUSTOMIZED_CONTENT_FOLDER)
                os.rename(self.temp_filename, os.path.join(settings.CUSTOMIZED_CONTENT_FOLDER, os.path.basename(self.temp_filename)))
                self.log.debug(os.path.join(settings.CUSTOMIZED_CONTENT_FOLDER, os.path.basename(self.temp_filename)))
                self.log.debug("Exists? %s", os.path.exists(os.path.join(settings.CUSTOMIZED_CONTENT_FOLDER, os.path.basename(self.temp_filename))))
            else:
                self.log.debug("Deleting customized content: '%s'", self.temp_filename)
                os.remove(self.temp_filename)
        self.deferred.callback(self.recipient)
    
    def onFailure(self, err):
        handle_recipient_failure(err, self.recipient, self.email_from, self.email_to, self.log)
        if self.recipient.send_status in (RECIPIENT_STATUS.ERROR, RECIPIENT_STATUS.GENERAL_ERROR) \
                and self.temp_filename and os.path.exists(self.temp_filename):
            self.log.debug("Deleting customized content: '%s'", self.temp_filename)
            os.remove(self.temp_filename)
        self.deferred.errback(err)

def handle_recipient_failure(err, recipient, email_from, email_to, log):
    assert(isinstance(recipient, MailingRecipient))
    if not recipient.in_progress:
        log.error("Programming error : trying to handle error on recipient <%s> not in progress. Skipped...", recipient)
        return
    domain_name = email_to.split('@')[1]
    if isinstance(err, Failure) and err.check(error.TimeoutError, 
                                              error.ConnectionLost,
                                              error.ConnectionRefusedError,
                                              error.ConnectError):
        err = Failure(smtp.SMTPClientError(None, str(err.value)))
    if isinstance(err, Failure) and isinstance(err.value, smtp.SMTPClientError):
        exc = err.value
        assert(isinstance(exc, smtp.SMTPClientError))
        # should have only one recipient
        if exc.addresses and len(exc.addresses) > 0:
            _email, code, resp = exc.addresses[0]
            if code in smtp.SUCCESS: # the error doesn't come from recipient but from email content or other...
                code = exc.code
                resp = exc.resp
        else:
            code = exc.code
            resp = exc.resp
        if not code or code < 500:
            log.warn("WARNING sending mailing FROM <%s> TO <%s>: %s", email_from, email_to, resp)
            logging.getLogger('mailing.out').warn("SOFTBOUNCED sending mailing FROM <%s> TO <%s>: %s", email_from, email_to, resp)
            recipient.update_send_status(RECIPIENT_STATUS.WARNING, smtp_code = code, smtp_message = resp, smtp_log = exc.log)
            recipient.set_send_mail_next_time()
            recipient.mark_as_finished()
            HourlyStats.add_try()
            DomainStats.add_try(domain_name)
            log.debug("Mailing [%s]: recipient <%s> postponed to %s", recipient.mail_from,
                                                                      recipient,
                                                                      recipient.next_try.isoformat(' '))
        else:
            log.error("ERROR sending mailing FROM <%s> TO <%s>: %s", email_from, email_to, resp)
            logging.getLogger('mailing.out').error("ERROR sending mailing FROM <%s> TO <%s>: %s", email_from, email_to, resp)
            recipient.update_send_status(RECIPIENT_STATUS.ERROR, smtp_code = code, smtp_message = resp, smtp_log = exc.log)
            recipient.mark_as_finished()
            HourlyStats.add_failed()
            DomainStats.add_failed(domain_name)
    else:
        log.error("ERROR sending mailing FROM <%s> TO <%s>: %s", email_from, email_to, str(err))
        logging.getLogger('mailing.out').error("ERROR sending mailing FROM <%s> TO <%s>", email_from, email_to)
        recipient.update_send_status(RECIPIENT_STATUS.GENERAL_ERROR, smtp_message = str(err))
        recipient.mark_as_finished()
        HourlyStats.add_failed()
        DomainStats.add_failed(domain_name)


