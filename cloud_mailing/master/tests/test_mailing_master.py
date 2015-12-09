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

import unittest
from bson import ObjectId
from twisted.trial.unittest import TestCase
from twisted.test import proto_helpers
from twisted.internet import reactor, defer, task
from twisted.spread import pb, util
from twisted.internet.protocol import ReconnectingClientFactory
from twisted.cred import credentials

from ...common import settings
from ...common.html_tools import strip_tags
from ...common.unittest_mixins import DatabaseMixin
from ..master_main import start_master_service, stop_master_service
from ..cloud_master import stop_all_threadpools
from ..cloud_master import MailingManagerView
from . import factories
from ..mailing_manager import MailingManager

from ..models import Mailing, MailingRecipient, MailingTempQueue, MAILING_STATUS, MailingHourlyStats, RECIPIENT_STATUS
from .. import models

import logging
import email
import email.header
import time
import hmac
from datetime import datetime, timedelta
import cPickle as pickle
from mogo import connect

def make_email():
    msg = email.mime.multipart.MIMEMultipart("alternative")

    html_content = u"<h1>Hi %%FIRST_NAME%%</h1>\n<p>This is the body of message.</p>\n<a href=\"%%UNSUBSCRIBE%%\">Click here to be removed</a>"
    plain_content = strip_tags(html_content)

    msg.attach(email.mime.text.MIMEText(plain_content.encode('utf-8'), 'plain', 'utf-8'))
    msg.attach(email.mime.text.MIMEText(html_content.encode('utf-8'), 'html', 'utf-8'))

    msg['X-Mailer'] = 'CloudMailing'
    msg['Subject'] = email.header.Header('Hi %%FIRST_NAME%%!', header_name='Subject')
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
        for recipient in MailingRecipient._get_collection().find({'_id': {'$in': map(lambda x: ObjectId(x), recipient_ids)}}):
            for field in ('contact_data', 'unsubscribe_id'):
                recipient.pop(field, None)
            recipient['_id'] = str(recipient['_id'])
            recipient['mailing'] = recipient['mailing'].id
            recipients_dict[recipient['_id']] = recipient
        return recipients_dict


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
        def1 = self.login(credentials.UsernamePassword(settings.SERIAL, hmac.HMAC("UT_SHARED_KEY").hexdigest()),
                          client=self.cloud_client)
        def1.addCallback(self.cloud_client.connected)


    def buildProtocol(self, addr):
        log.info('CloudClientFactory connected to %s' % addr)
        return pb.PBClientFactory.buildProtocol(self, addr)


class MailingMasterTest(DatabaseMixin, TestCase):
    # fixtures = ['mailing_sender', ]
    timeout = 10
    need_transactions = True

    def setUp(self):
        # logging.basicConfig(level=logging.WARN,
        #                     format='%(name)-12s: %(asctime)s %(levelname)-8s %(message)s',
        #                     )
        self.connect_to_db()
        self.master_port = 11620
        self.serverDisconnected = defer.Deferred()
        start_master_service(master_port=self.master_port, ssl_context_factory=None)

    def tearDown(self):
        #print "tearDown"
        stop_master_service()
        if self.clientConnection:
            self.clientConnection.disconnect()
            self.clientConnection = None
        # MailingRecipient.drop()
        # MailingTempQueue.drop()
        # Mailing.drop()
        # MailingHourlyStats.drop()
        self.cloud_client = None
        return defer.maybeDeferred(stop_all_threadpools)\
            .addBoth(lambda x: self.disconnect_from_db())

    def log(self, msg):
        print msg
        return msg

    def connect_client(self, disconnectedDeferred = None):
        d = defer.Deferred()
        self.cloud_client = CloudClient(d, disconnectedDeferred)
        factory = CloudClientFactory(self.cloud_client)
        master_ip, master_port = ('127.0.0.1', self.master_port)
        from twisted.internet import ssl
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
        if MailingTempQueue.count() >= recipients_count:
            return util.getAllPages(manager, 'get_recipients', 100)
        elif time.time() < t0 + 10.0:
            return task.deferLater(reactor, 0.1, self.do_get_recipients, manager, recipients_count, t0)
        print "MailingTempQueue.objects.count() = %d / recipients_count = %d" % (MailingTempQueue.count(), recipients_count)
        return defer.fail()

    def cb_get_recipients(self, data_list, recipients_count):
        # print "cb_get_recipients"
        recipients = pickle.loads(''.join(data_list))
        self.assertEquals(len(recipients), recipients_count)
        for recipient in recipients:
            self.assertTrue(isinstance(recipient, dict))
            self.assertTrue('_id' in recipient)
        return recipients

    def do_get_mailing(self, manager):
        #print "do_get_mailing"
        return util.getAllPages(manager, 'get_mailing', Mailing.first().id)

    def cb_get_mailing(self, data_list):
        # print "cb_get_mailing", data_list
        data = ''.join(data_list)
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
            MailingRecipient.create(mailing=mq, email=email, contact=repr({'email': email, 'firstname': 'Cedric%d' % i}),
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
        msg = make_email()
        recipients_count = 10
        self.fill_database(recipients_count)

        self.assertEquals(Mailing.count(), 1)
        self.assertEquals(MailingRecipient.count(), recipients_count)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        manager = MailingManager.getInstance()
        manager.forceToCheck()
        manager.checkState()

        return d

    def test_get_recipients_with_satellite_group(self):
        msg = make_email()
        recipients_count = 10
        self.fill_database(recipients_count, satellite_group='my-group')
        self.fill_database(recipients_count/2)    # another but with default group
        self.fill_database(recipients_count*2, satellite_group='not-my-group')    # third but with other group name

        client = models.CloudClient.first()
        client.group = 'my-group'
        client.save()

        self.assertEquals(Mailing.count(), 3)
        self.assertEquals(MailingRecipient.count(), recipients_count * 3.5)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        manager = MailingManager.getInstance()
        manager.forceToCheck()
        manager.checkState()

        return d

    def test_get_recipients_for_default_group(self):
        msg = make_email()
        recipients_count = 10
        self.fill_database(recipients_count/2, satellite_group='my-group')
        self.fill_database(recipients_count)    # another but with default group
        self.fill_database(recipients_count*2, satellite_group='not-my-group')    # third but with other group name

        self.assertEquals(Mailing.count(), 3)
        self.assertEquals(MailingRecipient.count(), recipients_count * 3.5)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        manager = MailingManager.getInstance()
        manager.forceToCheck()
        manager.checkState()

        return d

    def test_get_mailing(self):
        msg = make_email()
        recipients_count = 10
        self.fill_database(recipients_count)

        self.assertEquals(Mailing.count(), 1)
        self.assertEquals(MailingRecipient.count(), recipients_count)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_mailing)
        d.addCallback(self.cb_get_mailing)
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        return d

    def test_check_orphan_recipients(self):
        msg = make_email()
        recipients_count = 10
        self.fill_database(recipients_count)

        # need to force Temp queue filling
        manager = MailingManager.getInstance()
        manager.forceToCheck()
        manager.checkState()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)

        self.cloud_client.recipients = map(lambda x: x['_id'], MailingRecipient._get_collection().find(projection=[]))

        d.addCallback(self.cb_connected)

        t0 = time.time()
        d.addCallback(self.do_get_recipients, recipients_count, t0) # to ensure TempQueue is filled
        d.addCallback(self.cb_get_recipients, recipients_count)

        def check_handled_recipients(dummy, rcpts_count):
            self.assertEquals(rcpts_count, MailingTempQueue.find({'in_progress': True}).count())

        d.addCallback(check_handled_recipients, recipients_count)

        from ..cloud_master import mailing_portal
        mailing_master = mailing_portal.realm
        d.addCallback(lambda x: mailing_master.check_recipients_in_clients(since_hours=0))

        d.addCallback(check_handled_recipients, recipients_count)

        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        return d
        #return defer.DeferredList((d, d2,))

    def test_scheduled_start(self):
        recipients_count = 10
        self.fill_database(recipients_count)
        self.fill_database(recipients_count, scheduled_start=datetime.utcnow() + timedelta(hours=5))

        self.assertEquals(Mailing.count(), 2)
        self.assertEquals(MailingRecipient.count(), recipients_count*2)

        t0 = time.time()

        d2 = defer.Deferred()
        d = self.connect_client(disconnectedDeferred=d2)
        d.addCallback(self.cb_connected)
        d.addCallback(self.do_get_recipients, recipients_count, t0)
        d.addCallback(self.cb_get_recipients, recipients_count)  # only 10 recipient due to scheduled_start in the future
        d.addCallback(self.do_disconnect, d2)
        d.addErrback(self.do_disconnect_on_error, d2)

        manager = MailingManager.getInstance()
        manager.forceToCheck()
        manager.checkState()

        return d

    def test_scheduled_end(self):
        recipients_count = 10
        self.fill_database(recipients_count)
        self.fill_database(recipients_count, scheduled_end=datetime.utcnow() - timedelta(hours=5))

        self.assertEquals(Mailing.count(), 2)
        self.assertEquals(MailingRecipient.count(), recipients_count*2)

        t0 = time.time()
        manager = MailingManager.getInstance()
        manager.forceToCheck()

        d2 = defer.Deferred()
        d = manager.update_status_for_finished_mailings()
        d.addCallback(lambda x: manager.checkState())
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

        self.assertEquals(Mailing.count(), 2)
        self.assertEquals(MailingRecipient.count(), recipients_count*2)

        t0 = time.time()
        manager = MailingManager.getInstance()
        manager.forceToCheck()

        d2 = defer.Deferred()
        d = manager.update_status_for_finished_mailings()
        d.addCallback(lambda x: manager.checkState())
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
        self.assertEquals(100, len(r))
        self.assertEquals(1, len(mailings_stats))
        self.assertEquals(20, mailings_stats[ml.id]['total_softbounce'])
        self.assertEquals(50, mailings_stats[ml.id]['total_sent'])
        self.assertEquals(30, mailings_stats[ml.id]['total_error'])

        ids_ok = MailingManagerView._update_mailings_stats((r, mailings_stats))
        self.assertEqual(r, ids_ok)
        ml2 = Mailing.grab(ml.id)
        self.assertEquals(20, ml2.total_softbounce)
        self.assertEquals(50, ml2.total_sent)
        self.assertEquals(30, ml2.total_error)


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
            MailingRecipient.create( mailing=mq, email=email, contact=repr({'email': email, 'firstname': 'Cedric%d' % i}),
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
        self.assertEquals(MAILING_STATUS.FILLING_RECIPIENTS, mq.status)
        mq.activate()
        self.assertEquals(MAILING_STATUS.READY, mq.status)
        qs = Mailing.find(MailingManager.make_mailings_queryset())
        self.assertEqual(1, qs.count())

    def test_make_mailing_queryset_with_scheduled_duration(self):
        mq = factories.MailingFactory(scheduled_duration=14400)
        mq.activate()
        qs = Mailing.find(MailingManager.make_mailings_queryset())
        self.assertEqual(1, qs.count())

    # @override_settings(DEBUG=True)
    def test_make_mailing_queryset_on_filling_recipients_mailing(self):
        logging.getLogger('django.db_conn.backends').setLevel(logging.DEBUG)

        mq = factories.MailingFactory()
        self.assertEquals(MAILING_STATUS.FILLING_RECIPIENTS, mq.status)
        qs = Mailing.find(MailingManager.make_mailings_queryset())
        self.assertEqual(0, qs.count())

    def test_make_recipients_queryset(self):
        mq = self._fill_database(10)
        mailing = Mailing.find_one(MailingManager.make_mailings_queryset())
        qs = MailingRecipient.find(MailingManager.make_recipients_queryset(mailing))
        self.assertEqual(10, qs.count())

    def test_make_recipients_queryset_on_greylisted_entries(self):
        mq = self._fill_database(10, real_start=datetime.now() - timedelta(hours=10))
        MailingRecipient.update({'email': 'rcpt1@free.fr'}, {'$set': {'first_try': datetime.now() - timedelta(hours=10),
                                                           'next_try': datetime.utcnow() - timedelta(hours=1),
                                                           'send_status': RECIPIENT_STATUS.WARNING}})
        MailingRecipient.update({'email': 'rcpt2@free.fr'}, {'$set': {'first_try': datetime.now() - timedelta(hours=10),
                                                           'next_try': datetime.utcnow() + timedelta(hours=1),
                                                           'send_status': RECIPIENT_STATUS.WARNING}})
        mailing = Mailing.find_one(MailingManager.make_mailings_queryset())
        qs = MailingRecipient.find(MailingManager.make_recipients_queryset(mailing))
        self.assertEqual(9, qs.count())
