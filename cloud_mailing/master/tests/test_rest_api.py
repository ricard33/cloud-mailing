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
from cloud_mailing.master.tests import factories
import json
from twisted.web.http_headers import Headers
from twisted.internet import reactor
from twisted.trial.unittest import TestCase

from cloud_mailing.common import http_status
from ...common.unittest_mixins import CommonTestMixin, DatabaseMixin, RestApiTestMixin

__author__ = 'Cedric RICARD'

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

        d = self.call_api('GET', '/', http_status.HTTP_200_OK)
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
        d = self.call_api('GET', "/mailings", http_status.HTTP_200_OK)
        d.addCallback(lambda x: self.assertTrue(isinstance(x, list)) and x)
        d.addCallback(lambda x: self.assertEqual(len(x), 1) and x)
        d.addCallback(lambda x: self.assertEqual(x[0]['sender_name'], "Mailing Sender") and x)

        return d

    def test_get_mailing(self):
        """
        List all mailings
        """
        ml = factories.MailingFactory()
        d = self.call_api('GET', "/mailings/%d" % ml.id, http_status.HTTP_200_OK)
        d.addCallback(lambda x: self.assertTrue(isinstance(x, dict)) and x)
        d.addCallback(lambda x: self.assertEqual(x['id'], ml.id) and x)

        return d