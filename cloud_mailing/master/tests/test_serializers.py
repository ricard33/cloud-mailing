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
from twisted.trial.unittest import TestCase

from ..models import RECIPIENT_STATUS, MAILING_STATUS
from . import factories
from ..serializers import RecipientSerializer, Serializer, MailingSerializer
from ...common.unittest_mixins import CommonTestMixin, DatabaseMixin
from .unittest_mixins import RestApiTestMixin

__author__ = 'Cedric RICARD'


class SerializerTestCase(CommonTestMixin, DatabaseMixin, RestApiTestMixin, TestCase):

    def setUp(self):
        self.connect_to_db()
        self.start_rest_api()
        self.setup_settings()

    def tearDown(self):
        self.clear_settings()
        return self.stop_rest_api().addBoth(lambda x: self.disconnect_from_db())

    def test_make_filter(self):
        self.assertDictEqual({'field': 1}, Serializer().make_filter({'field': 1}))
        self.assertDictEqual({'field': {'$regex': '.*value.*'}}, Serializer().make_filter({'field': 'value'}))
        self.assertDictEqual({'field': {'$in': (1, 2)}}, Serializer().make_filter({'field': (1, 2)}))
        self.assertDictEqual({'field': {'$in': ('1', '2')}}, Serializer().make_filter({'field': ('1', '2')}))


class MailingSerializerTestCase(CommonTestMixin, DatabaseMixin, RestApiTestMixin, TestCase):

    def setUp(self):
        self.connect_to_db()
        self.start_rest_api()
        self.setup_settings()

    def tearDown(self):
        self.clear_settings()
        return self.stop_rest_api().addBoth(lambda x: self.disconnect_from_db())

    def test_make_filter(self):
        self.assertDictEqual({'domain_name': 'value'}, MailingSerializer().make_filter({'domain': 'value'}))
        self.assertDictEqual({'domain_name': {'$in': (1, 2)}}, MailingSerializer().make_filter({'domain': (1, 2)}))
        self.assertDictEqual({'_id': {'$in': [1]}}, MailingSerializer().make_filter({'id': 1}))
        self.assertDictEqual({'_id': {'$in': (1, 2)}}, MailingSerializer().make_filter({'id': (1, 2)}))
        self.assertDictEqual({'status': {'$in': [MAILING_STATUS.FINISHED]}},
                             MailingSerializer().make_filter({'status': MAILING_STATUS.FINISHED}))
        self.assertDictEqual({'status': {'$in': [MAILING_STATUS.READY, MAILING_STATUS.FINISHED]}},
                             MailingSerializer().make_filter({'status': (MAILING_STATUS.READY, MAILING_STATUS.FINISHED)}))
        self.assertDictEqual({'owner_guid': 'value'}, MailingSerializer().make_filter({'owner_guid': 'value'}))
        self.assertDictEqual({'owner_guid': {'$in': ('value1', 'value2')}}, MailingSerializer().make_filter({'owner_guid': ('value1', 'value2')}))
        self.assertDictEqual({'satellite_group': 'value'}, MailingSerializer().make_filter({'satellite_group': 'value'}))
        self.assertDictEqual({'satellite_group': {'$in': ('value1', 'value2')}}, MailingSerializer().make_filter({'satellite_group': ('value1', 'value2')}))


class RecipientSerializerTestCase(CommonTestMixin, DatabaseMixin, RestApiTestMixin, TestCase):

    def setUp(self):
        self.connect_to_db()
        self.start_rest_api()
        self.setup_settings()

    def tearDown(self):
        self.clear_settings()
        return self.stop_rest_api().addBoth(lambda x: self.disconnect_from_db())

    def test_filtered_field(self):

        self.assertIn('tracking_id', RecipientSerializer().filtered_fields)
        self.assertIn('tracking_id', RecipientSerializer(fields_filter='none').filtered_fields)

    def test_make_filter(self):
        self.assertDictEqual({'mailing.$id': 1}, RecipientSerializer().make_filter({'mailing': 1}))
        self.assertDictEqual({'mailing.$id': {'$in': (1, 2)}}, RecipientSerializer().make_filter({'mailing': (1, 2)}))
        self.assertDictEqual({'$and': [{'$or': [
            {'reply_code': 'Error'},
            {'reply_text': {'$regex': '.*Error.*'}},
        ]}]}, RecipientSerializer().make_filter({'smtp_reply': 'Error'}))
