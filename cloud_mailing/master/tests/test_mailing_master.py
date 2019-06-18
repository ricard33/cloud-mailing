# Copyright 2015-2019 Cedric RICARD
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
import email
import email.message
import hmac
import logging
import os
import time
from datetime import datetime, timedelta

from bson import ObjectId
from twisted.cred import credentials
from twisted.internet import reactor, defer, task
from twisted.spread import pb, util
from twisted.spread.util import CallbackPageCollector
from twisted.trial.unittest import TestCase

from ...common.encoding import force_bytes
from .. import settings_vars
from ..send_recipients_task import SendRecipientsTask
from . import factories
from .. import models
from ..cloud_master import MailingManagerView
from ..cloud_master import stop_all_threadpools
from ..mailing_manager import MailingManager
from ..master_main import start_master_service, stop_master_service
from ..models import Mailing, MailingRecipient, MAILING_STATUS, RECIPIENT_STATUS
from ...common import settings
from ...common.html_tools import strip_tags
from ...common.unittest_mixins import DatabaseMixin


def make_email():
    msg = email.message.EmailMessage()

    html_content = "<h1>Hi %%FIRST_NAME%%</h1>\n<p>This is the body of message.</p>\n<a href=\"%%UNSUBSCRIBE%%\">Click here to be removed</a>"
    plain_content = strip_tags(html_content)

    msg.set_content(plain_content)
    msg.add_alternative(html_content, subtype='html')

    msg['X-Mailer'] = 'CloudMailing'
    msg['Subject'] = 'Hi %%FIRST_NAME%%!'
    msg['From'] = 'user1@my-domain.com'
    msg['To'] = 'mailing@my-domain.com'
    msg['Date'] = email.utils.formatdate()
    # msg['Message-ID'] = email.utils.make_msgid()  # can be very slow !!!
    msg['Message-ID'] = "UT"
    return msg

log = logging.getLogger("ut")


class CloudClient(pb.Referenceable):
    def __init__(self, connectedDeferred, disconnectedDeferred):
        self.master = None
        self.is_connected = False
        self.mailing_queue = None
        self.ut_mode = False
        self.recipients = []
        self.connectedDeferred = connectedDeferred
        self.disconnectedDeferred = disconnectedDeferred
        self.get_recipients_deferred = defer.Deferred()

    def remote_is_ready(self):
        return True

    def disconnected(self, remoteRef):
        log.info("Master disconnected!! %s", remoteRef)
        self.is_connected = False
        if self.disconnectedDeferred:
            self.disconnectedDeferred.callback(remoteRef)

    def connected(self, master):
        log.info("Master connected!! %s", master)
        self.master = master
        self.is_connected = True
        self.master.notifyOnDisconnect(self.disconnected)
        self.master.callRemote('get_mailing_manager') \
            .addCallback(self.cb_get_mailing_manager)

    def cb_get_mailing_manager(self, mailing_manager):
        self.mailing_manager = mailing_manager
        assert(isinstance(self.connectedDeferred, defer.Deferred))
        if self.connectedDeferred:
            self.connectedDeferred.callback(self.mailing_manager)

    def remote_activate_unittest_mode(self, activated):
        log.debug("UnitTest Mode set to %s", activated)
        self.ut_mode = activated

    def remote_close_mailing(self, mailing_id):
        """Ask queue to remove all recipients from this mailing id."""
        pass

    def remote_get_recipients_list(self):
        """
        Returns the list of currently handled recipient ids.
        """
        return self.recipients

    def remote_check_recipients(self, recipient_ids):
        """
        Returns a dictionary mapping for each input id the corresponding recipient object, nor None is not found.
        """
        recipients_dict = {}
        for _id in recipient_ids:
            recipients_dict[_id] = None
        for recipient in MailingRecipient._get_collection().find({'_id': {'$in': [ObjectId(x) for x in recipient_ids]}}):
            for field in ('contact_data', 'unsubscribe_id'):
                recipient.pop(field, None)
            recipient['_id'] = str(recipient['_id'])
            recipient['mailing'] = recipient['mailing'].id
            recipients_dict[recipient['_id']] = recipient
        return recipients_dict

    def remote_prepare_getting_recipients(self, count):
        """
        Ask satellite for how many recipients he want, and for its paging collector.
        The satellite should return a tuple (wanted_count, collector)
        :param count: proposed recipients count
        :return: a deferred
        """
        d = defer.Deferred()
        collector = CallbackPageCollector(d.callback)
        d.addCallbacks(self.cb_get_recipients, None, callbackArgs=[time.time()])
        return count, collector

    def cb_get_recipients(self, data_list, t0):
        recipients = pickle.loads(b''.join(data_list))
        # print "Received %d new recipients from Manager in %.1fs." % (len(recipients), time.time() - t0)
        self.get_recipients_deferred.callback(recipients)




class CloudClientFactory(pb.PBClientFactory):

    cloud_client = None

    def __init__(self, cloud_client):
        pb.PBClientFactory.__init__(self)
        self.ipaddress = None
        self.cloud_client = cloud_client
        self.maxDelay = 300  # Max delay for ReconnectingClientFactory

    def clientConnectionMade(self, broker):
        log.info('Started to connect.')
        # self.resetDelay()
        pb.PBClientFactory.clientConnectionMade(self, broker)
        def1 = self.login(credentials.UsernamePassword(settings.SERIAL,
                                                       force_bytes(hmac.HMAC(b"UT_SHARED_KEY").hexdigest())),
                          client=self.cloud_client)
        def1.addCallback(self.cloud_client.connected)


    def buildProtocol(self, addr):
        log.info('CloudClientFactory connected to %s' % addr)
        return pb.PBClientFactory.buildProtocol(self, addr)


class MailingMasterTest(DatabaseMixin, TestCase):
    timeout = 10
    need_transactions = True

    def setUp(self):
        # logging.basicConfig(level=logging.WARN,
        #                     format='%(name)-12s: %(asctime)s %(levelname)-8s %(message)s',
        #                     )
        logging.getLogger().setLevel(logging.ERROR)
        self.connect_to_db()
        self.master_port = 11620
        self.serverDisconnected = defer.Deferred()
        start_master_service(master_port=self.master_port, ssl_context_factory=None)

    def tearDown(self):
        #print "tearDown"
        stop_master_service()
        if hasattr(self, "clientConnection") and self.clientConnection:
            self.clientConnection.disconnect()
            self.clientConnection = None
        # MailingRecipient.drop()
        # Mailing.drop()
        # MailingHourlyStats.drop()
        self.cloud_client = None
        return defer.maybeDeferred(stop_all_threadpools)\
            .addBoth(lambda x: self.disconnect_from_db())

    def log(self, msg):
        print(msg)
        return msg

    def connect_client(self, disconnectedDeferred = None):
        d = defer.Deferred()
        self.cloud_client = CloudClient(d, disconnectedDeferred)
        factory = CloudClientFactory(self.cloud_client)
        master_ip, master_port = ('127.0.0.1', self.master_port)
        #pylint: disable-msg=E1101
        log.info('Trying to connect to Master on %s:%d' % (master_ip, master_port))
        #noinspection PyUnresolvedReferences
        self.clientConnection = reactor.connectTCP(master_ip, master_port, factory)
        return d

    def test_client_connection(self):
        # d2 = defer.Deferred()
        d = self.connect_client()
        d.addCallback(lambda manager: self.clientConnection.disconnect())
        return d

    def cb_connected(self, manager):
        # print 'Connected!!'
        return manager

    def do_get_recipients(self, manager, recipients_count, t0):
        # print "do_get_recipients"
        SendRecipientsTask.getInstance()._send_recipients_to_satellite(settings.SERIAL, 100)
        return self.cloud_client.get_recipients_deferred
        # return util.getAllPages(manager, 'get_recipients', 100)

    def cb_get_recipients(self, recipients, recipients_count):
        # print "cb_get_recipients", type(data_list), data_list, recipients_count
        # recipients = pickle.loads(''.join(data_list))
        self.assertEqual(len(recipients), recipients_count)
        for recipient in recipients:
            self.assertTrue(isinstance(recipient, dict))
            self.assertTrue('_id' in recipient)
        return recipients

    def do_get_mailing(self, manager):
        #print "do_get_mailing"
        return util.getAllPages(manager, 'get_mailing', Mailing.first().id)

    def cb_get_mailing(self, data_list):
        # print "cb_get_mailing", data_list
        data = b''.join(data_list)
        mailing_id = None
        mailing_dict = pickle.loads(data)
        original = Mailing.grab(mailing_dict['id'])
        self.assertFalse(mailing_dict['delete'])
        #self.assertEquals(mailing_dict['header'], original.header)
        #self.assertEquals(mailing_dict['body'], original.body)
        return mailing_id

    def do_disconnect(self, dummy, disconnect_deferred):
        #print "disconnect"
        if self.clientConnection:
            self.clientConnection.disconnect()
        self.clientConnection = None
        return disconnect_deferred

    def do_disconnect_on_error(self, err, disconnect_deferred):
        self.do_disconnect(None, disconnect_deferred)
        return err

    def fill_database(self, recipients_count, scheduled_start=None, scheduled_end=None, scheduled_duration=None,
                      real_start=None, satellite_group=None):
        mq = factories.MailingFactory(satellite_group=satellite_group)
        for i in range(recipients_count):
            email = 'rcpt%d@free.fr' % i
            MailingRecipient.create(mailing=mq, email=email, domain_name=email.split('@', 1)[1],
                                    contact=repr({'email': email, 'firstname': 'Cedric%d' % i}),
                                    next_try=datetime.utcnow())

        mq.status = MAILING_STATUS.READY
        if scheduled_start:
            mq.scheduled_start = scheduled_start
        if scheduled_end:
            mq.scheduled_end = scheduled_end
        if scheduled_duration:
            mq.scheduled_duration = scheduled_duration
        if real_start:
            mq.status = MAILING_STATUS.RUNNING
            mq.start_time = real_start
        mq.update_stats()
        mq.save()

    def test_get_recipients(self):
        # msg = make_email()
        recipients_count = 10
        self.fill_database(recipients_count)

        self.assertEqual(Mailing.count(), 1)
        self.assertEqual(MailingRecipient.count(), recipients_count)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        return d

    def test_get_recipients_with_satellite_group(self):
        # msg = make_email()
        recipients_count = 10
        self.fill_database(recipients_count, satellite_group='my-group')
        self.fill_database(int(recipients_count / 2))  # another but with default group
        self.fill_database(recipients_count * 2, satellite_group='not-my-group')  # third but with other group name

        client = models.CloudClient.first()
        client.group = 'my-group'
        client.save()

        self.assertEqual(Mailing.count(), 3)
        self.assertEqual(MailingRecipient.count(), recipients_count * 3.5)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        manager = MailingManager.getInstance()

        return d

    def test_get_recipients_for_default_group(self):
        # msg = make_email()
        recipients_count = 10
        self.fill_database(int(recipients_count / 2), satellite_group='my-group')
        self.fill_database(recipients_count)  # another but with default group
        self.fill_database(recipients_count * 2, satellite_group='not-my-group')  # third but with other group name

        self.assertEqual(Mailing.count(), 3)
        self.assertEqual(MailingRecipient.count(), recipients_count * 3.5)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        manager = MailingManager.getInstance()

        return d

    def test_get_mailing(self):
        # msg = make_email()
        recipients_count = 10
        self.fill_database(recipients_count)

        self.assertEqual(Mailing.count(), 1)
        self.assertEqual(MailingRecipient.count(), recipients_count)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_mailing)
        d.addCallback(self.cb_get_mailing)
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        return d

    @defer.inlineCallbacks
    def test_check_orphan_recipients(self):
        # msg = make_email()
        recipients_count = 10
        self.fill_database(recipients_count)

        # need to force Temp queue filling
        manager = MailingManager.getInstance()

        d2 = defer.Deferred()
        manager = yield self.connect_client(disconnectedDeferred=d2)

        self.cloud_client.recipients = [x['_id'] for x in MailingRecipient._get_collection().find(projection=[])]

        t0 = time.time()
        recipients = yield self.do_get_recipients(manager, recipients_count, t0) # to ensure TempQueue is filled
        self.assertEqual(recipients_count, len(recipients))
        self.assertEqual(recipients_count, MailingRecipient.find({'in_progress': True}).count())

        from ..cloud_master import mailing_portal
        mailing_master = mailing_portal.realm

        # Recipients are still actives in satellite, no one should be removed
        yield mailing_master.check_recipients_in_clients(since_seconds=0)
        self.assertEqual(recipients_count, MailingRecipient.find({'in_progress': True}).count())

        self.clientConnection.disconnect()
        # yield d2
        yield task.deferLater(reactor, 0.1, lambda: None)  # Wait for master to know that client is disconnected

        # satellite is disconnected, but too recently: no one should be removed
        yield mailing_master.check_recipients_in_clients(since_seconds=60)
        self.assertEqual(recipients_count, MailingRecipient.find({'in_progress': True}).count())

        # satellite is disconnected for time: recipients should be removed
        yield mailing_master.check_recipients_in_clients(since_seconds=-10)
        self.assertEqual(0, MailingRecipient.find({'in_progress': True}).count())

        yield d2

    def test_scheduled_start(self):
        recipients_count = 10
        self.fill_database(recipients_count)
        self.fill_database(recipients_count, scheduled_start=datetime.utcnow() + timedelta(hours=5))

        self.assertEqual(Mailing.count(), 2)
        self.assertEqual(MailingRecipient.count(), recipients_count*2)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)  # only 10 recipient due to scheduled_start in the future
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        manager = MailingManager.getInstance()

        return d

    def test_scheduled_end(self):
        recipients_count = 10
        self.fill_database(recipients_count)
        self.fill_database(recipients_count, scheduled_end=datetime.utcnow() - timedelta(hours=5))

        self.assertEqual(Mailing.count(), 2)
        self.assertEqual(MailingRecipient.count(), recipients_count*2)

        t0 = time.time()
        manager = MailingManager.getInstance()

        d2 = defer.Deferred()
        d = manager.update_status_for_finished_mailings()
        d.addCallback(lambda x: self.connect_client(disconnectedDeferred=d2))
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)  # only 10 recipient due to scheduled_end in the past
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        return d

    def test_scheduled_duration(self):
        recipients_count = 10
        self.fill_database(recipients_count)
        self.fill_database(recipients_count, real_start=datetime.utcnow() - timedelta(hours=5), scheduled_duration=60)

        self.assertEqual(Mailing.count(), 2)
        self.assertEqual(MailingRecipient.count(), recipients_count*2)

        t0 = time.time()
        manager = MailingManager.getInstance()

        d2 = defer.Deferred()
        d = manager.update_status_for_finished_mailings()
        d.addCallback(lambda x: self.connect_client(disconnectedDeferred=d2))
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)  # only 10 recipient due to low scheduled_duration
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        return d


class SendReportTest(DatabaseMixin, TestCase):

    def setUp(self):
        self.connect_to_db()

    def tearDown(self):
        self.disconnect_from_db()

    def test_store_reports(self):
        ml = factories.MailingFactory()
        ids = [factories.RecipientFactory(mailing=ml, email='email%d@domain.tld' % i).id for i in range(100)]

        recipients = [
            {
                'email': 'email%d@domain.tld' % i,
                '_id' : ids[i],
                'mailing': ml.id,
                'first_try': datetime.now(),
                'try_count': 1,
                'send_status': i < 50 and RECIPIENT_STATUS.FINISHED or i < 80 and RECIPIENT_STATUS.ERROR or RECIPIENT_STATUS.WARNING,
                'reply_code': 250,
                'reply_enhanced_code': "2.5.0",
                'reply_text': "Ok",
                'smtp_log': "The full log...",
            } for i in range(len(ids))
        ]
        r, mailings_stats = MailingManagerView._store_reports(recipients, "SERIAL", logging.getLogger())
        self.assertEqual(100, len(r))
        self.assertEqual(1, len(mailings_stats))
        self.assertEqual(20, mailings_stats[ml.id]['total_softbounce'])
        self.assertEqual(50, mailings_stats[ml.id]['total_sent'])
        self.assertEqual(30, mailings_stats[ml.id]['total_error'])

        ids_ok = MailingManagerView._update_mailings_stats((r, mailings_stats))
        self.assertEqual(r, ids_ok)
        ml2 = Mailing.grab(ml.id)
        self.assertEqual(20, ml2.total_softbounce)
        self.assertEqual(50, ml2.total_sent)
        self.assertEqual(30, ml2.total_error)


class MailingManagerQueries(DatabaseMixin, TestCase):

    def setUp(self):
        self.connect_to_db()

    def tearDown(self):
        self.disconnect_from_db()

    def _fill_database(self, recipients_count, scheduled_start=None, scheduled_end=None, scheduled_duration=None,
                      real_start=None):
        mq = factories.MailingFactory()
        for i in range(recipients_count):
            email = 'rcpt%d@free.fr' % i
            MailingRecipient.create( mailing=mq, email=email, domain_name=email.split('@', 1)[1],
                                     contact=repr({'email': email, 'firstname': 'Cedric%d' % i}),
                                 next_try=datetime.utcnow())

        mq.status = MAILING_STATUS.READY
        if scheduled_start:
            mq.scheduled_start = scheduled_start
        if scheduled_end:
            mq.scheduled_end = scheduled_end
        if scheduled_duration:
            mq.scheduled_duration = scheduled_duration
        if real_start:
            mq.status = MAILING_STATUS.RUNNING
            mq.start_time = real_start
        mq.update_stats()
        mq.save()
        return mq

    def test_make_mailing_queryset(self):
        mq = factories.MailingFactory()
        self.assertEqual(MAILING_STATUS.FILLING_RECIPIENTS, mq.status)
        mq.activate()
        self.assertEqual(MAILING_STATUS.READY, mq.status)
        qs = Mailing.find(SendRecipientsTask.make_mailings_queryset())
        self.assertEqual(1, qs.count())

    def test_make_mailing_queryset_with_scheduled_duration(self):
        mq = factories.MailingFactory(scheduled_duration=14400)
        mq.activate()
        qs = Mailing.find(SendRecipientsTask.make_mailings_queryset())
        self.assertEqual(1, qs.count())

    # @override_settings(DEBUG=True)
    def test_make_mailing_queryset_on_filling_recipients_mailing(self):
        logging.getLogger('django.db_conn.backends').setLevel(logging.DEBUG)

        mq = factories.MailingFactory()
        self.assertEqual(MAILING_STATUS.FILLING_RECIPIENTS, mq.status)
        qs = Mailing.find(SendRecipientsTask.make_mailings_queryset())
        self.assertEqual(0, qs.count())

    def test_make_recipients_queryset(self):
        mq = self._fill_database(10)
        mailing = Mailing.find_one(SendRecipientsTask.make_mailings_queryset())
        qs = MailingRecipient.find(SendRecipientsTask.make_recipients_queryset(mailing.id))
        self.assertEqual(10, qs.count())

    def test_make_recipients_queryset_on_greylisted_entries(self):
        mq = self._fill_database(10, real_start=datetime.now() - timedelta(hours=10))
        MailingRecipient.update({'email': 'rcpt1@free.fr'}, {'$set': {'first_try': datetime.now() - timedelta(hours=10),
                                                           'next_try': datetime.utcnow() - timedelta(hours=1),
                                                           'send_status': RECIPIENT_STATUS.WARNING}})
        MailingRecipient.update({'email': 'rcpt2@free.fr'}, {'$set': {'first_try': datetime.now() - timedelta(hours=10),
                                                           'next_try': datetime.utcnow() + timedelta(hours=1),
                                                           'send_status': RECIPIENT_STATUS.WARNING}})
        mailing = Mailing.find_one(SendRecipientsTask.make_mailings_queryset())
        qs = MailingRecipient.find(SendRecipientsTask.make_recipients_queryset(mailing.id))
        self.assertEqual(9, qs.count())


class CustomizedContentTest(DatabaseMixin, TestCase):
    def setUp(self):
        self.connect_to_db()

    def tearDown(self):
        self.disconnect_from_db()

    def test_purge(self):
        fname = os.path.join(settings.CUSTOMIZED_CONTENT_FOLDER, 'cust_ml_UT.rfc822')
        with open(fname, 'w') as f:
            f.write("XXX")

        self.assertTrue(os.path.exists(fname))
        manager = MailingManager.getInstance()

        manager.purge_customized_content()
        self.assertTrue(os.path.exists(fname))

        os.utime(fname, (time.time(), time.time() - (settings_vars.get_int(settings_vars.CUSTOMIZED_CONTENT_RETENTION_DAYS) + 1) * 86400))

        # logging.basicConfig(level=1)
        manager.purge_customized_content()
        self.assertFalse(os.path.exists(fname))
