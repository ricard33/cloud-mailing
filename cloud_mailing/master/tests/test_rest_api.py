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

from datetime import datetime
import base64

from ..models import MAILING_STATUS, Mailing
from . import factories
import json
from twisted.web.http_headers import Headers
from twisted.internet import reactor
from twisted.trial.unittest import TestCase

from ...common import http_status
from ...common.unittest_mixins import CommonTestMixin, DatabaseMixin
from .unittest_mixins import RestApiTestMixin

__author__ = 'Cedric RICARD'


class AuthenticationTestCase(CommonTestMixin, DatabaseMixin, RestApiTestMixin, TestCase):

    def setUp(self):
        self.connect_to_db()
        self.start_rest_api()
        self.setup_settings()

    def tearDown(self):
        self.clear_settings()
        return self.stop_rest_api().addBoth(lambda x: self.disconnect_from_db())

    def test_authenticate(self):

        def cb_response(response):
            assert(isinstance(response.headers, Headers))
            # print(response.headers)
            self.assertTrue(response.headers.hasHeader('set-cookie'))
            return response

        def cbBody(body):
            # print body
            self.assertEqual("admin", body['username'])
            self.assertEqual(True, body['is_superuser'])

        d = self.call_api(b'POST', '/authenticate', http_status.HTTP_200_OK,
                          # credentials=('admin', self.api_key),
                          data={'username': 'admin', 'password': self.api_key}, pre_read_body_cb=cb_response)
        d.addCallback(cbBody)

        return d

    def test_unauthenticated(self):
        d = self.call_api(b'GET', '/mailings', http_status.HTTP_403_FORBIDDEN)

        return d

    def test_logout(self):

        d = self.call_api(b'POST', '/authenticate', http_status.HTTP_200_OK,
                          data={'username': 'admin', 'password': self.api_key})
        d.addCallback(lambda x: self.call_api(b'GET', "/mailings", http_status.HTTP_200_OK))
        d.addCallback(lambda x: self.call_api(b'POST', "/logout", http_status.HTTP_200_OK))
        d.addCallback(lambda x: self.call_api(b'GET', "/mailings", http_status.HTTP_403_FORBIDDEN))

        return d


class HomeTestCase(CommonTestMixin, DatabaseMixin, RestApiTestMixin, TestCase):

    def setUp(self):
        self.connect_to_db()
        self.start_rest_api()
        self.setup_settings()

    def tearDown(self):
        self.clear_settings()
        return self.stop_rest_api().addBoth(lambda x: self.disconnect_from_db())

    def test_get_version(self):

        def cbBody(body):
            # print body
            self.assertEqual("CloudMailing", body['product_name'])
            self.assertIn("product_version", body)
            self.assertIn("api_version", body)

        d = self.call_api('GET', '', http_status.HTTP_200_OK)  # unauthenticated is allowed
        d.addCallback(cbBody)

        return d


class MailingTestCase(CommonTestMixin, DatabaseMixin, RestApiTestMixin, TestCase):

    def setUp(self):
        self.connect_to_db()
        self.start_rest_api()
        self.setup_settings()

    def tearDown(self):
        self.clear_settings()
        return self.stop_rest_api().addBoth(lambda x: self.disconnect_from_db())

    def test_list_mailings(self):
        """
        List all mailings
        """
        factories.MailingFactory()
        d = self.call_api('GET', "/mailings", http_status.HTTP_200_OK, credentials=('admin', self.api_key))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x['items'], list)) and x)
        d.addCallback(lambda x: self.assertEqual(1, len(x['items'])) and x)
        d.addCallback(lambda x: self.assertEqual("Mailing Sender", x['items'][0]['sender_name']) and x)
        return d

    def test_get_mailing(self):
        """
        Get a mailing details
        """
        ml = factories.MailingFactory()
        d = self.call_api('GET', "/mailings/%d" % ml.id, http_status.HTTP_200_OK, credentials=('admin', self.api_key))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertEqual(x['id'], ml.id) and x)
        return d

    def test_get_mailings_count(self):
        """
        Count mailings
        """
        factories.MailingFactory()
        factories.MailingFactory()
        d = self.call_api('GET', "/mailings/?.filter=total", http_status.HTTP_200_OK, credentials=('admin', self.api_key))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x['items'], list)) and x)
        d.addCallback(lambda x: self.assertEqual(x['total'], 2) and x)
        d.addCallback(lambda x: self.assertEqual(len(x['items']), 2) and x)
        return d


    def test_set_mailing_properties(self):
        """
        Test mailing properties
        """
        mailing = factories.MailingFactory()
        now = datetime.now()

        d = self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'mail_from': 'a@other-domain.fr'}, credentials=('admin', self.api_key))
        d.addCallback(lambda x: self.call_api('GET', "/mailings/%d" % mailing.id, http_status.HTTP_200_OK))
        d.addCallback(lambda x: self.assertEqual(x['domain_name'], "other-domain.fr") and x)

        d.addCallback(lambda x: self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'tracking_url': 'https://www.example.com/m/',
                                                                                                 'header': "Subject: New subject!"}))
        d.addCallback(lambda x: self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'scheduled_start': now.isoformat(),
                                                                                                 'scheduled_duration': 3600}))
        d.addCallback(lambda x: self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'scheduled_start': now.isoformat()+"Z",  # with TZ
                                                                                                 'scheduled_duration': 3600}))
        d.addCallback(lambda x: self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'owner_guid': "UT", }))

        d.addCallback(lambda x: self.call_api('GET', "/mailings/%d" % mailing.id, http_status.HTTP_200_OK))
        d.addCallback(lambda x: self.assertEqual("New subject!", x['subject']) and x)
        d.addCallback(lambda x: self.assertEqual(now.isoformat()[:23], x['scheduled_start'][:23]) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x['scheduled_duration'], int)) and x)
        # Test if GUID is correctly set
        d.addCallback(lambda x: self.call_api('GET', "/mailings/%d" % mailing.id))
        # d.addCallback(lambda x: self.log(x))
        d.addCallback(lambda x: self.assertEqual("UT", x['owner_guid']) and x)
        return d

    def test_start_mailing(self):
        """
        Test mailings sending
        """
        mailing = factories.MailingFactory()
        # factories.RecipientFactory(mailing=mailing)

        d = self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'status': 'RUNNING'}, credentials=('admin', self.api_key))
        d.addCallback(lambda x: self.assertEqual(MAILING_STATUS.READY, x['status']) and x)
        return d

    def test_pause_and_restart_mailing_ready(self):
        mailing = factories.MailingFactory(status=MAILING_STATUS.READY)
        # factories.RecipientFactory(mailing=mailing)

        d = self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'status': 'PAUSED'}, credentials=('admin', self.api_key))
        d.addCallback(lambda x: self.assertEqual(MAILING_STATUS.PAUSED, x['status']) and x)
        d.addCallback(lambda x: self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'status': 'RUNNING'}))
        d.addCallback(lambda x: self.assertEqual(MAILING_STATUS.READY, x['status']) and x)
        return d

    def test_pause_and_restart_mailing_running(self):
        mailing = factories.MailingFactory(status=MAILING_STATUS.RUNNING, start_time=datetime.utcnow())
        # factories.RecipientFactory(mailing=mailing)

        d = self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'status': 'PAUSED'}, credentials=('admin', self.api_key))
        d.addCallback(lambda x: self.assertEqual(MAILING_STATUS.PAUSED, x['status']) and x)
        d.addCallback(lambda x: self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'status': 'RUNNING'}))
        d.addCallback(lambda x: self.assertEqual(MAILING_STATUS.RUNNING, x['status']) and x)
        return d

    def test_stop_mailing(self):
        mailing = factories.MailingFactory(status=MAILING_STATUS.RUNNING, start_time=datetime.utcnow())

        d = self.call_api('PATCH', "/mailings/%d" % mailing.id, data={'status': 'FINISHED'}, credentials=('admin', self.api_key))
        d.addCallback(lambda x: self.assertEqual(MAILING_STATUS.FINISHED, x['status']) and x)
        return d

    def test_delete_mailing(self):
        mailing = factories.MailingFactory(status=MAILING_STATUS.RUNNING, start_time=datetime.utcnow())

        d = self.call_api('DELETE', "/mailings/%d" % mailing.id, expected_status_code=http_status.HTTP_204_NO_CONTENT, credentials=(b'admin', self.api_key))
        d.addCallback(lambda x: self.assertEqual(None, Mailing.find({'_id': mailing.id}).first()))
        return d


class RecipientTestCase(CommonTestMixin, DatabaseMixin, RestApiTestMixin, TestCase):

    def setUp(self):
        self.connect_to_db()
        self.start_rest_api()
        self.setup_settings()

    def tearDown(self):
        self.clear_settings()
        return self.stop_rest_api().addBoth(lambda x: self.disconnect_from_db())

    def test_list_recipients(self):
        """
        List all recipients of a mailing
        """
        factories.RecipientFactory()
        factories.RecipientFactory()
        d = self.call_api('GET', "/recipients", http_status.HTTP_200_OK, credentials=('admin', self.api_key))
        # d.addCallback(lambda x: self.log(x))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x['items'], list)) and x)
        d.addCallback(lambda x: self.assertEqual(2, len(x['items'])) and x)
        d.addCallback(lambda x: self.assertIn('email', x['items'][0]) and x)

        # d.addCallback(lambda x: self.assertEqual("Mailing Sender", x['items'][0]['sender_name']) and x)
        return d

    def test_list_recipients_from_mailing(self):
        """
        List all recipients of a mailing
        """
        ml = factories.MailingFactory()
        factories.RecipientFactory(mailing=ml)
        factories.RecipientFactory(mailing=ml)
        factories.RecipientFactory()
        d = self.call_api('GET', "/recipients?mailing=%d" % ml.id, http_status.HTTP_200_OK, credentials=('admin', self.api_key))
        # d.addCallback(lambda x: self.log(x))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x['items'], list)) and x)
        d.addCallback(lambda x: self.assertEqual(2, len(x['items'])) and x)
        d.addCallback(lambda x: self.assertIn('email', x['items'][0]) and x)

        # d.addCallback(lambda x: self.assertEqual("Mailing Sender", x['items'][0]['sender_name']) and x)
        return d

    def test_list_recipients_nested_api(self):
        """
        List all recipients of a mailing
        """
        ml = factories.MailingFactory()
        factories.RecipientFactory(mailing=ml)
        factories.RecipientFactory(mailing=ml)
        factories.RecipientFactory()
        d = self.call_api('GET', "/mailings/%d/recipients" % ml.id, http_status.HTTP_200_OK, credentials=('admin', self.api_key))
        # d.addCallback(lambda x: self.log(x))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x['items'], list)) and x)
        d.addCallback(lambda x: self.assertEqual(2, len(x['items'])) and x)
        d.addCallback(lambda x: self.assertIn('email', x['items'][0]) and x)

        # d.addCallback(lambda x: self.assertEqual("Mailing Sender", x['items'][0]['sender_name']) and x)
        return d

    def test_get_recipient(self):
        """
        Get a recipient details
        """
        ml = factories.MailingFactory()
        rcpt = factories.RecipientFactory(mailing=ml)
        # WARNING: API should never use `id` but `tracking_id` to get recipients
        d = self.call_api('GET', "/mailings/%d/recipients/%s" % (ml.id, rcpt.tracking_id), http_status.HTTP_200_OK, credentials=('admin', self.api_key))
        # d.addCallback(lambda x: self.log(x))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertEqual(x['id'], rcpt.tracking_id) and x)
        return d

    def test_get_recipients_count(self):
        """
        Count total recipients
        """
        factories.RecipientFactory()
        factories.RecipientFactory()
        factories.RecipientFactory()
        d = self.call_api('GET', "/recipients/?.filter=total", http_status.HTTP_200_OK, credentials=('admin', self.api_key))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x['items'], list)) and x)
        d.addCallback(lambda x: self.assertEqual(x['total'], 3) and x)
        d.addCallback(lambda x: self.assertEqual(len(x['items']), 3) and x)
        return d


    def test_get_recipients_count_from_mailing(self):
        """
        Count mailing recipients
        """
        ml = factories.MailingFactory()
        factories.RecipientFactory(mailing=ml)
        factories.RecipientFactory(mailing=ml)
        factories.RecipientFactory()  # Another recipient from another mailing. Should not be counted.
        d = self.call_api('GET', "/mailings/%d/recipients/?.filter=total" % ml.id, http_status.HTTP_200_OK, credentials=('admin', self.api_key))
        # d.addCallback(lambda x: self.log(x))
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertTrue(isinstance(x['items'], list)) and x)
        d.addCallback(lambda x: self.assertEqual(x['total'], 2) and x)
        d.addCallback(lambda x: self.assertEqual(len(x['items']), 2) and x)
        return d


