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

import base64
import email
import logging
from datetime import datetime, timedelta
import os

from twisted.internet import reactor
from twisted.trial.unittest import TestCase
from twisted.web import server, xmlrpc

from ...common.db_common import get_db
from ..send_recipients_task import SendRecipientsTask
from . import factories

from ...common.unittest_mixins import DatabaseMixin
from ..cloud_master import MailingManagerView
from .factories import MailingFactory, RecipientFactory, CloudClientFactory
from ...common.models import Settings
from ..xmlrpc_api import CloudMailingRpc
from ..models import Mailing, MAILING_STATUS, RECIPIENT_STATUS, MailingHourlyStats, MailingRecipient
from ...common import settings
from ...common.config_file import ConfigFile


# def out(s):
#     # print s, Mailing.objects.all().count()
#     return True


class XmlRpcMailingTestCase(DatabaseMixin, TestCase):

    def setUp(self):
        self.connect_to_db()
        self.__proxy = None
        self.p = reactor.listenTCP(0, server.Site(CloudMailingRpc(useDateTime=True)),
                                    interface="127.0.0.1")
        self.port = self.p.getHost().port
        Settings.set('TEST_MODE', True)
        config = ConfigFile()
        config.read(settings.CONFIG_FILE)

        config.set('CM_MASTER', 'API_KEY', 'the_API_key')
        if not os.path.exists(settings.CONFIG_PATH):
            os.makedirs(settings.CONFIG_PATH)
        with open(settings.CONFIG_FILE, 'wt') as fp:
            config.write(fp)

    def tearDown(self):
        if os.path.exists(settings.CONFIG_FILE):
            os.remove(settings.CONFIG_FILE)
        self.__proxy = None
        return self.p.stopListening().addBoth(lambda x: self.disconnect_from_db())

    def log(self, msg):
        print(msg)
        return msg

    def proxy(self):
        """
        Return a new xmlrpc.Proxy for the test site created in
        setUp(), using the given factory as the queryFactory, or
        self.queryFactory if no factory is provided.
        """
        if not self.__proxy:
            self.__proxy = xmlrpc.Proxy(b"http://admin:the_API_key@127.0.0.1:%d/" % self.port, useDateTime=True, allowNone=True)
        return self.__proxy

    def test_get_satellites_count(self):
        CloudClientFactory()
        d = self.proxy().callRemote("cloud_get_satellites_count")
        d.addCallback(lambda x: self.assertEqual(x, 1) and x)
        return d

    def test_list_satellites(self):
        CloudClientFactory()
        d = self.proxy().callRemote("cloud_list_satellites")
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        return d

    def test_add_satellite(self):
        CloudClientFactory()
        d = self.proxy().callRemote("cloud_add_satellite", 'CXM_OTHER', {'enabled': False})
        d.addCallback(lambda x: self.proxy().callRemote("cloud_list_satellites"))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 2) and x)
        return d

    def test_set_satellite_properties_old_affinity_format(self):
        s = CloudClientFactory()
        d = self.proxy().callRemote("cloud_set_satellite_properties", s.id, {
            'serial': 'CXM_CHANGED',
            'enabled': False,
            'shared_key': 'X'*40,
            'domain_affinity': "{'orange.fr': True, 'free.fr': False}"
        })
        d.addCallback(lambda x: self.proxy().callRemote("cloud_list_satellites"))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual('CXM_CHANGED', x[0]['serial']) and x)
        return d

    def test_set_satellite_properties(self):
        s = CloudClientFactory()
        d = self.proxy().callRemote("cloud_set_satellite_properties", s.id, {
            'serial': 'CXM_CHANGED',
            'enabled': False,
            'shared_key': 'X'*40,
            'domain_affinity': {'include': ['orange.fr'], 'exclude': ['free.fr']}
        })
        d.addCallback(lambda x: self.proxy().callRemote("cloud_list_satellites"))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual('CXM_CHANGED', x[0]['serial']) and x)
        return d

    def test_delete_satellite_(self):
        s = CloudClientFactory()
        d = self.proxy().callRemote("cloud_delete_satellite", s.id)
        d.addCallback(lambda x: self.proxy().callRemote("cloud_list_satellites"))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)
        return d

    def test_get_mailings_count(self):
        """
        Count all mailings
        """
        MailingFactory()
        d = self.proxy().callRemote("get_mailings_count")
        d.addCallback(lambda x: self.assertEqual(x, 1) and x)
        d.addCallback(lambda x: MailingFactory())
        d.addCallback(lambda x: self.proxy().callRemote("get_mailings_count"))
        d.addCallback(lambda x: self.assertEqual(x, 2) and x)

        return d

    def test_get_mailings_count_with_filter(self):
        """
        Count all mailings matching a filter
        """
        MailingFactory(mail_from="sender@my-company.biz")
        d = self.proxy().callRemote("get_mailings_count", {'domain': ["my-company.biz"]})
        d.addCallback(lambda x: self.assertEqual(x, 1) and x)
        d.addCallback(lambda x: self.proxy().callRemote("get_mailings_count", {'domain': ["other.com"]}))
        d.addCallback(lambda x: self.assertEqual(x, 0) and x)
        d.addCallback(lambda x: self.proxy().callRemote("get_mailings_count", {'status': ["FILLING_RECIPIENTS"]}))
        d.addCallback(lambda x: self.assertEqual(x, 1) and x)
        d.addCallback(lambda x: self.proxy().callRemote("get_mailings_count", {'status': ["READY"]}))
        d.addCallback(lambda x: self.assertEqual(x, 0) and x)

        return d

    def test_list_mailings(self):
        """
        List all mailings
        """
        MailingFactory()
        d = self.proxy().callRemote("list_mailings")
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['sender_name'], "Mailing Sender") and x)

        return d

    def test_list_mailings_with_filter_on_domain(self):
        """
        List all mailings with old filter based on domain name
        """
        MailingFactory()

        d = self.proxy().callRemote("list_mailings", "my-company.biz")
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['sender_name'], "Mailing Sender") and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-company.com"))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)
        return d

    def test_list_mailings_with_filter(self):
        """
        List all mailings using new filters
        """
        ml = MailingFactory()
        ml.owner_guid = "UT"
        ml.save()

        d = self.proxy().callRemote("list_mailings", {'domain': ["my-company.biz"]})
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['sender_name'], "Mailing Sender") and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", {'domain': ["my-company.com"]}))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", {'id': [ml.id, 999]}))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", {'id': [999]}))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", {'status': ["FILLING_RECIPIENTS"]}))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", {'status': ["READY"]}))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", {'owner_guid': ["UT"]}))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", {'owner_guid': ["OTHER"]}))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        return d

    def test_create_mailing(self):
        """
        Test mailings creation
        """
        d = self.proxy().callRemote("list_mailings", "my-domain.com")
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("create_mailing", "mailing@my-domain.com", "My Domain", "New Mailing",
                                                        b"<h1>Title</h1><p>blabla</p>", b"", "utf-8"))
        d.addCallback(lambda x: self.assertTrue(x > 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['mail_from'], "mailing@my-domain.com") and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['domain_name'], "my-domain.com") and x)

        return d

    def test_create_mailing_with_probably_encoding_problem(self):
        """
        If mailing content is updated by set_mailing_properties(), transport_encoding seems to be incorrect
        In this test, this content reveals the bug because of the '=de' sequence, interpreted as valid
        hexa code for Quoted-Printable encoding (but it isn't QP encoded!).
        """
        content = """<html>
<head><title></title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <meta name="viewport" content="width=320, target-densitydpi=device-dpi">
</head><body>=dc </body></html>"""

        d = self.proxy().callRemote("list_mailings", "my-domain.com")
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("create_mailing", "mailing@my-domain.com", "My Domain", "New Mailing",
                                                        "", "", "utf-8"))
        d.addCallback(lambda x: self.assertTrue(x > 0) and x)
        # d.addCallback(lambda x: sys.stderr.write(Mailing.objects.all()[0].content.body))

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("set_mailing_properties", x[0]['id'], {
            'html_content': content,
            'plain_content': "New content",
            'charset' : "iso-8859-15",
            }))

        # d.addCallback(lambda x: sys.stderr.write(Mailing.objects.all()[0].content.body))
        d.addCallback(lambda x: self.assertTrue('content="text/html; charset=utf-8"' in
            email.message_from_bytes(Mailing.first().header
                                      + Mailing.first().body).get_payload()[1].get_payload(decode=True).decode('utf-8')))

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        #twice to be sure to have QP transfer encoding
        d.addCallback(lambda x: self.proxy().callRemote("set_mailing_properties", x[0]['id'], {
            'html_content': content,
            'plain_content': "New content",
            'charset' : "utf-8",
            }))

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        # d.addCallback(lambda x: sys.stderr.write(Mailing.objects.all()[0].content.body))
        d.addCallback(lambda x: self.assertTrue('content="text/html; charset=utf-8"' in
            email.message_from_bytes(Mailing.first().header
                                      + Mailing.first().body).get_payload()[1].get_payload(decode=True).decode('utf-8')))


        return d

    def test_create_mailing_ext(self):
        """
        Test mailings creation using rfc822 form
        """
        with open(os.path.join(os.path.dirname(__file__), 'data', 'crash_due_to_us-ascii_charset.rfc822'), 'rt') as f:
            content = f.read()
        content_b64 = base64.b64encode(content.encode())
        d = self.proxy().callRemote("list_mailings", "my-domain.com")
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("create_mailing_ext", content_b64))
        d.addCallback(lambda x: self.assertTrue(x > 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['mail_from'], "mailing@my-domain.com") and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['domain_name'], "my-domain.com") and x)

        return d

    def test_start_mailing(self):
        """
        Test mailings creation and sending
        """
        d = self.proxy().callRemote("list_mailings", "my-domain.com")
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("create_mailing", "mailing@my-domain.com", "My Domain", "New Mailing",
                                                        "<h1>Title</h1><p>blabla</p>", "", "utf-8"))
        d.addCallback(lambda x: self.assertTrue(x > 0) and x)
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.FILLING_RECIPIENTS) and x)

        d.addCallback(lambda x: self.proxy().callRemote("start_mailing", x[0]['id']))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.READY) and x)
        return d

    def test_pause_mailing(self):
        mailing = factories.MailingFactory(status=MAILING_STATUS.RUNNING, start_time=datetime.utcnow())

        d = self.proxy().callRemote("pause_mailing", mailing.id)
        d.addCallback(lambda x: self.assertEqual(x, MAILING_STATUS.PAUSED) and x)
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.PAUSED) and x)
        d.addCallback(lambda x: self.proxy().callRemote("start_mailing", mailing.id))
        d.addCallback(lambda x: self.assertEqual(x, MAILING_STATUS.RUNNING) and x)
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.RUNNING) and x)
        return d

    def test_set_mailing_properties(self):
        """
        Test mailing properties
        """
        mailing = MailingFactory()

        d = self.proxy().callRemote("set_mailing_properties", mailing.id, {'mail_from': 'a@other-domain.fr'})
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['domain_name'], "other-domain.fr") and x)

        d.addCallback(lambda x: self.proxy().callRemote("set_mailing_properties", mailing.id, {'tracking_url': 'https://www.example.com/m/',
                                                                                                 'header': "Subject: New subject!"}))
        d.addCallback(lambda x: self.proxy().callRemote("set_mailing_properties", mailing.id, {'scheduled_start': datetime.now().isoformat(),
                                                                                                 'scheduled_duration': 3600}))
        d.addCallback(lambda x: self.proxy().callRemote("set_mailing_properties", mailing.id, {'owner_guid': "UT", }))

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(b"Subject: New subject!\n\n", x[0]['header'].data) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x[0]['scheduled_start'], datetime)) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x[0]['scheduled_duration'], int)) and x)
        # Test if GUID is correctly set
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", {'owner_guid': ["UT"]}))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        return d

    def test_change_subject_and_content(self):
        """
        Test mailing properties
        """
        mailing = MailingFactory()

        d = self.proxy().callRemote("set_mailing_properties", mailing.id, {'mail_from': 'a@other-domain.fr'})
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['domain_name'], "other-domain.fr") and x)

        d.addCallback(lambda x: self.proxy().callRemote("set_mailing_properties", mailing.id, {
            'tracking_url': 'https://www.example.com/m/',
            'subject': "New subject!",
            'html_content': "<html><body>New content</body></html>",
            'plain_content': "New content",
            'charset' : "utf-8",
            }))

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x[0])

        def decode_header(mailing):
            mailing['header'] = mailing['header'].data
            return mailing
        d.addCallback(decode_header)
        d.addCallback(lambda x: self.assertTrue(b"Subject: New subject!" in x['header']) and x)
        return d

    def test_set_empty_subject(self):
        """
        Test mailing properties
        """
        mailing = MailingFactory()

        d = self.proxy().callRemote("set_mailing_properties", mailing.id, {
            'subject': '',
            'charset' : "utf-8",
            })
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        # d.addCallback(lambda x: self.assertEqual(x[0]['subject'], "") and x)
        d.addCallback(lambda x: self.log(x[0]['header']) and x)
        d.addCallback(lambda x: self.assertTrue(b"Subject:\n" in x[0]['header'].data) and x)
        return d

    def test_delete_mailing(self):
        """
        Tests mailing deletion
        """
        mailing = MailingFactory()
        RecipientFactory(mailing=mailing, email="1@2.fr")
        RecipientFactory(mailing=mailing, email="2@2.fr")
        RecipientFactory(mailing=mailing, email="3@2.fr")
        RecipientFactory(mailing=mailing, email="4@2.fr")
        d = self.proxy().callRemote("list_mailings", "my-company.biz")
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("delete_mailing", mailing.id))
        d.addCallback(lambda x: self.assertEqual(x, 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-company.biz"))
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)
        return d

    def test_delete_all_mailings_for_a_domain(self):
        """
        Tests mailing deletion
        """
        MailingFactory(mail_from = "sender@my-company.biz")
        MailingFactory(mail_from="from@another-domain.com")
        d = self.proxy().callRemote("list_mailings")
        d.addCallback(lambda x: self.assertEqual(len(x), 2) and x)
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-company.biz"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("delete_all_mailings_for_domain", "my-company.biz"))
        d.addCallback(lambda x: self.assertEqual(x, 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings"))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("delete_all_mailings_for_domain", "another-domain.com"))
        d.addCallback(lambda x: self.assertEqual(x, 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("list_mailings"))
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)
        return d

    def test_add_recipient(self):
        mailing = MailingFactory()
        d = self.proxy().callRemote("add_recipients", mailing.id, [{'email': "new_rcpt@world.com"}])
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x[0])
        d.addCallback(lambda rcpt: self.assertTrue(isinstance(rcpt, dict)) and rcpt)
        d.addCallback(lambda rcpt: self.assertEqual("new_rcpt@world.com", rcpt['email']) and rcpt)
        return d

    def test_add_recipients(self):
        mailing = MailingFactory()
        d = self.proxy().callRemote("add_recipients", mailing.id, [
            {'email': "new_rcpt@world.com",},
            {'email': "another_one@ici.fr",},
            {'email': "again@its.me"},
        ])
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 3) and x)

        d.addCallback(lambda x: self.assertEqual("new_rcpt@world.com", x[0]['email']) and x)
        d.addCallback(lambda x: self.assertTrue("id" in x[0]) and x)
        d.addCallback(lambda x: self.assertEqual("another_one@ici.fr", x[1]['email']) and x)
        d.addCallback(lambda x: self.assertTrue("id" in x[1]) and x)
        d.addCallback(lambda x: self.assertEqual("again@its.me", x[2]['email']) and x)
        d.addCallback(lambda x: self.assertTrue("id" in x[2]) and x)
        return d

    def test_send_test(self):
        mailing = MailingFactory()
        d = self.proxy().callRemote("send_test", mailing.id, [
            {'email': "new_rcpt@world.com",},
            {'email': "another_one@ici.fr",},
            {'email': "again@its.me"},
        ])
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 3) and x)

        d.addCallback(lambda x: self.assertEqual("new_rcpt@world.com", x[0]['email']) and x)
        d.addCallback(lambda x: self.assertTrue("id" in x[0]) and x)
        d.addCallback(lambda x: self.assertEqual("another_one@ici.fr", x[1]['email']) and x)
        d.addCallback(lambda x: self.assertTrue("id" in x[1]) and x)
        d.addCallback(lambda x: self.assertEqual("again@its.me", x[2]['email']) and x)
        d.addCallback(lambda x: self.assertTrue("id" in x[2]) and x)

        # Test emails should be available for Satellites
        d.addCallback(lambda x: self.db.mailingrecipient.find(SendRecipientsTask.make_recipients_queryset(mailing.id, only_primary=True)))
        d.addCallback(lambda x: self.assertEqual(3, len(x)))

        return d

    def test_get_recipients_status(self):
        """
        Tests recipient status retrieve
        """
        mailing = MailingFactory()
        ids = []
        ids.append(RecipientFactory(mailing=mailing, email="1@2.fr").tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="2@2.fr").tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="3@2.fr", contact={'first_name': 'John', 'last_name': 'DOE'}).tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="4@2.fr").tracking_id)
        d = self.proxy().callRemote("list_mailings", "my-company.biz")
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status", list(map(str, ids))))
        d.addCallback(lambda x: self.assertEqual(len(x), 4) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], RECIPIENT_STATUS.READY) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status", [str(ids[2])]))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertNotIn('contact', x[0]) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status", [str(ids[2])], {'with_contact_data': True}))
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertIn('contact', x[0]) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['contact']['first_name'], 'John') and x)

        return d

    def test_get_recipients_status_updated_since(self):
        """
        Tests recipient status retrieve
        """
        mailing = MailingFactory()
        ids = []
        ids.append(RecipientFactory(mailing=mailing, email="1@2.fr", send_status=RECIPIENT_STATUS.FINISHED).tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="2@2.fr", send_status=RECIPIENT_STATUS.FINISHED).tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="3@2.fr", send_status=RECIPIENT_STATUS.FINISHED, report_ready=True).tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="4@2.fr", send_status=RECIPIENT_STATUS.FINISHED).tracking_id)
        d = self.proxy().callRemote("list_mailings", "my-company.biz")
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since"))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 4) and x)

        return d

    def test_get_recipients_status_updated_since_with_filter(self):
        """
        Tests recipient status retrieve
        """
        mailing = MailingFactory(owner_guid='the_owner')
        mailing2 = MailingFactory(owner_guid='another')
        ids = []
        ids.append(RecipientFactory(mailing=mailing, email="1@2.fr", send_status=RECIPIENT_STATUS.READY).tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="2@2.fr", send_status=RECIPIENT_STATUS.IN_PROGRESS).tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="3@2.fr", send_status=RECIPIENT_STATUS.FINISHED).tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="4@2.fr", send_status=RECIPIENT_STATUS.FINISHED, report_ready=True).tracking_id)
        ids.append(RecipientFactory(mailing=mailing, email="5@2.fr", send_status=RECIPIENT_STATUS.WARNING).tracking_id)
        ids.append(RecipientFactory(mailing=mailing2, email="6@2.fr", send_status=RECIPIENT_STATUS.ERROR).tracking_id)
        d = self.proxy().callRemote("list_mailings", "my-company.biz")
        d.addCallback(lambda x: self.assertEqual(len(x), 2) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since", None, {}))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 5) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since", None, {'status': ('WARNING', 'ERROR')}))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 2) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since", None, {'owners': ('the_owner', 'other')}))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 4) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since", None, {'owners': ('other',)}))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since", None, {'sender_domains': ('other.com',)}))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since", None, {'sender_domains': (mailing.domain_name, 'other.com',)}))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 5) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since", None, {'mailings': [mailing.id]}))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 4) and x)

        return d

    def test_get_recipients_status_updated_since_with_options(self):
        """
        Tests recipient status retrieve
        """
        mailing = MailingFactory(owner_guid='the_owner')
        rcpt1 = RecipientFactory(mailing=mailing, email="1@2.fr", send_status=RECIPIENT_STATUS.FINISHED,
                                 contact={'first_name': 'John', 'last_name': 'DOE'})
        d = self.proxy().callRemote("list_mailings", "my-company.biz")
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since", None, {}, 1000, {}))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 1) and x['recipients'])
        d.addCallback(lambda x: self.assertNotIn('contact', x[0]) and x)

        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_status_updated_since", None, {}, 1000, {'with_contact_data': True}))
        d.addCallback(lambda x: self.assertEqual(len(x['recipients']), 1) and x['recipients'])
        d.addCallback(lambda x: self.assertIn('contact', x[0]) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['contact']['first_name'], 'John') and x)

        return d

    def test_purge_empty_mailing(self):
        """
        Test mailings purge if empty
        """
        d = self.proxy().callRemote("list_mailings", "my-domain.com")
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("create_mailing", "mailing@my-domain.com", "My Domain", "New Mailing",
                                                        "<h1>Title</h1><p>blabla</p>", "", "utf-8"))
        d.addCallback(lambda x: self.assertTrue(x > 0) and x)
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.FILLING_RECIPIENTS) and x)

        d.addCallback(lambda x: self.proxy().callRemote("start_mailing", x[0]['id']))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(1, len(x)) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.READY) and x)
        d.addCallback(lambda x: self.proxy().callRemote("force_purge_empty_mailings"))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(1, len(x)) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.FINISHED) and x)
        return d

    def test_dont_purge_non_empty_mailing(self):
        """
        Test mailings purge if empty
        """
        d = self.proxy().callRemote("list_mailings", "my-domain.com")
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("create_mailing", "mailing@my-domain.com", "My Domain", "New Mailing",
                                                        "<h1>Title</h1><p>blabla</p>", "", "utf-8"))
        d.addCallback(lambda x: self.assertTrue(x > 0) and x)
        d.addCallback(lambda x: self.proxy().callRemote("add_recipients", x, [
            {'email': "new_rcpt@world.com",},
            {'email': "another_one@ici.fr",},
            {'email': "again@its.me"},
        ]))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.FILLING_RECIPIENTS) and x)

        d.addCallback(lambda x: self.proxy().callRemote("start_mailing", x[0]['id']))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(1, len(x)) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.READY) and x)
        d.addCallback(lambda x: self.proxy().callRemote("force_purge_empty_mailings"))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(1, len(x)) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.READY) and x)
        return d

    def test_dont_purge_permanent_mailings(self):
        """
        Test permanent mailings (without end date)
        """
        d = self.proxy().callRemote("list_mailings", "my-domain.com")
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("create_mailing", "mailing@my-domain.com", "My Domain", "New Mailing",
                                                        "<h1>Title</h1><p>blabla</p>", "", "utf-8"))
        d.addCallback(lambda x: self.assertTrue(x > 0) and x)
        d.addCallback(lambda x: self.proxy().callRemote("set_mailing_properties", x, {'type': 'OPENED'}))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.FILLING_RECIPIENTS) and x)

        d.addCallback(lambda x: self.proxy().callRemote("start_mailing", x[0]['id']))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(1, len(x)) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.READY) and x)
        d.addCallback(lambda x: self.proxy().callRemote("force_purge_empty_mailings"))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(1, len(x)) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.READY) and x)
        return d

    def test_dont_purge_mailings_with_flag_dont_close(self):
        """
        Test standard mailings purge if 'dont_close_if_empty' flag is set.
        """
        d = self.proxy().callRemote("list_mailings", "my-domain.com")
        d.addCallback(lambda x: self.assertEqual(len(x), 0) and x)

        d.addCallback(lambda x: self.proxy().callRemote("create_mailing", "mailing@my-domain.com", "My Domain", "New Mailing",
                                                        "<h1>Title</h1><p>blabla</p>", "", "utf-8"))
        d.addCallback(lambda x: self.assertTrue(x > 0) and x)
        d.addCallback(lambda x: self.proxy().callRemote("set_mailing_properties", x, {'type': 'REGULAR', 'dont_close_if_empty': True}))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.FILLING_RECIPIENTS) and x)

        d.addCallback(lambda x: self.proxy().callRemote("start_mailing", x[0]['id']))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(1, len(x)) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.READY) and x)
        d.addCallback(lambda x: self.proxy().callRemote("force_purge_empty_mailings"))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(1, len(x)) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.READY) and x)

        d.addCallback(lambda x: self.proxy().callRemote("set_mailing_properties", x[0]['id'], {'dont_close_if_empty': False}))
        d.addCallback(lambda x: self.proxy().callRemote("force_purge_empty_mailings"))
        d.addCallback(lambda x: self.proxy().callRemote("list_mailings", "my-domain.com"))
        d.addCallback(lambda x: self.assertEqual(1, len(x)) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['status'], MAILING_STATUS.FINISHED) and x)
        return d

    def test_get_hourly_statistics(self):
        MailingHourlyStats.add_try('SERIAL')
        MailingHourlyStats.add_sent('SERIAL')
        MailingHourlyStats.add_failed('SERIAL')
        d = self.proxy().callRemote("get_hourly_statistics", {'from_date': datetime.utcnow().replace(minute=0, second=0, microsecond=0)})

        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['tries'], 3) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['sent'], 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['failed'], 1) and x)
        return d

    def test_reset_recipient_status(self):
        """
        Tests reset recipients status
        """
        mailing = MailingFactory()
        RecipientFactory(mailing=mailing, email="1@2.fr", send_status=RECIPIENT_STATUS.ERROR)
        RecipientFactory(mailing=mailing, email="2@2.fr", send_status=RECIPIENT_STATUS.FINISHED)
        RecipientFactory(mailing=mailing, email="3@2.fr", send_status=RECIPIENT_STATUS.ERROR)
        RecipientFactory(mailing=mailing, email="4@2.fr", send_status=RECIPIENT_STATUS.FINISHED)

        ids = [
            MailingRecipient.find_one({'email': "1@2.fr"}).tracking_id,
            MailingRecipient.find_one({'email': "2@2.fr"}).tracking_id,
        ]

        d = self.proxy().callRemote("reset_recipients_status", list(map(str, ids)))
        d.addCallback(lambda x: self.assertEqual(MailingRecipient.find_one({'email': "1@2.fr"}).send_status, RECIPIENT_STATUS.READY) and x)
        d.addCallback(lambda x: self.assertEqual(MailingRecipient.find_one({'email': "2@2.fr"}).send_status, RECIPIENT_STATUS.READY) and x)
        d.addCallback(lambda x: self.assertEqual(MailingRecipient.find_one({'email': "3@2.fr"}).send_status, RECIPIENT_STATUS.ERROR) and x)
        d.addCallback(lambda x: self.assertEqual(MailingRecipient.find_one({'email': "4@2.fr"}).send_status, RECIPIENT_STATUS.FINISHED) and x)
        return d

    def test_get_recipients_count(self):
        """
        Count all recipients matching a filter
        """
        ml = MailingFactory(mail_from="sender@my-company.biz")
        RecipientFactory(mailing=ml, send_status=RECIPIENT_STATUS.FINISHED)
        RecipientFactory(mailing=ml, send_status=RECIPIENT_STATUS.ERROR)
        RecipientFactory(mailing=ml)
        RecipientFactory(mailing=MailingFactory(mail_from="sender@other.com"), send_status=RECIPIENT_STATUS.FINISHED)
        d = self.proxy().callRemote("get_recipients_count")
        d.addCallback(lambda x: self.assertEqual(x, 4) and x)
        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_count", {'sender_domains': ["my-company.biz"]}))
        d.addCallback(lambda x: self.assertEqual(x, 3) and x)
        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_count", {'mailings': [ml.id]}))
        d.addCallback(lambda x: self.assertEqual(x, 3) and x)
        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_count", {'status': [RECIPIENT_STATUS.FINISHED]}))
        d.addCallback(lambda x: self.assertEqual(x, 2) and x)
        d.addCallback(lambda x: self.proxy().callRemote("get_recipients_count", {'status': [RECIPIENT_STATUS.READY]}))
        d.addCallback(lambda x: self.assertEqual(x, 1) and x)

        return d

