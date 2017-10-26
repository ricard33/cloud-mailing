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

from bson import ObjectId, DBRef
from datetime import datetime
from twisted.trial import unittest

from ...common.unittest_mixins import DatabaseMixin
from ..db_initialization import do_migrations, init_master_db, migrations, _0001_remove_temp_queue
from . import factories

__author__ = 'Cedric RICARD'


class MigrationsTestCase(DatabaseMixin, unittest.TestCase):

    def setUp(self):
        self.connect_to_db()

    def tearDown(self):
        self.disconnect_from_db()

    def test_initialize_on_empty_database(self):
        init_master_db(self.db_sync)
        self.assertIn('_migrations', self.db_sync.collection_names(include_system_collections=False))
        self.assertEqual(len(migrations), self.db_sync['_migrations'].count())

    def test_on_empty_database(self):
        do_migrations(self.db_sync)
        self.assertIn('_migrations', self.db_sync.collection_names(include_system_collections=False))
        self.assertEqual(len(migrations), self.db_sync['_migrations'].count())

    def test_0001_remove_temp_queue(self):
        client = factories.CloudClientFactory()
        mailing = factories.MailingFactory()
        result1 = self.db_sync.mailingrecipient.insert_one({
            "next_try" : datetime(2016, 0o3, 16, 0o6, 23, 0o6, 826000),
            "in_progress" : False,
            "send_status" : "READY",
            "contact" : {
                "company" : "The company",
                "email" : "email13@my-company.biz"
            },
            "tracking_id" : "9fabe1ae-6da7-496b-bd85-3b492b9b4d49",
            "mailing" : DBRef("mailing", mailing.id),
            "email" : "email13@my-company.biz",
        })
        result2 = self.db_sync.mailingrecipient.insert_one({
            "next_try" : datetime(2016, 0o3, 16, 0o6, 23, 0o6, 826000),
            "in_progress" : True,
            "send_status" : "READY",
            "contact" : {
                "company" : "The company",
                "email" : "email565@my-company.biz"
            },
            "tracking_id" : "9fabe1ae-6da7-496b-bd85-3b492b9b4d49",
            "mailing" : DBRef("mailing", mailing.id),
            "email" : "email565@my-company.biz",
        })
        self.db_sync.mailingtempqueue.insert_one({
            "mail_from" : "sender@cloud-mailing.net",
            "next_try" : datetime(2016, 0o3, 16, 0o6, 23, 0o6, 826000),
            "sender_name" : "CM Tests",
            "recipient" : self.db_sync.mailingrecipient.find_one({'_id': result2.inserted_id}),
            "in_progress" : True,
            "client": DBRef("cloudclient", client.id),
            "date_delegated": datetime.now(),
            "mailing": DBRef("mailing", mailing.id),
            "email" : "email565@my-company.biz",
            "domain_name" : "my-company.biz"
        })
        result3 = self.db_sync.mailingrecipient.insert_one({
            "next_try" : datetime(2016, 0o3, 16, 0o6, 23, 0o6, 826000),
            "in_progress" : True,
            "send_status" : "READY",
            "contact" : {
                "company" : "The company",
                "email" : "email777@my-company.biz"
            },
            "tracking_id" : "9fabe1ae-6da7-496b-bd85-3b492b9b4d49",
            "mailing" : DBRef("mailing", mailing.id),
            "email" : "email777@my-company.biz",
        })

        _0001_remove_temp_queue(self.db_sync)

        recipient = self.db_sync.mailingrecipient.find_one({'_id': result1.inserted_id})
        self.assertEqual('my-company.biz', recipient['domain_name'])
        self.assertEqual(False, recipient['in_progress'])

        recipient = self.db_sync.mailingrecipient.find_one({'_id': result2.inserted_id})
        self.assertEqual('my-company.biz', recipient['domain_name'])
        self.assertEqual(True, recipient['in_progress'])
        self.assertEqual(client.serial, recipient['cloud_client'])
        self.assertIn('date_delegated', recipient)

        recipient = self.db_sync.mailingrecipient.find_one({'_id': result3.inserted_id})
        self.assertEqual('my-company.biz', recipient['domain_name'])
        self.assertEqual(False, recipient['in_progress'])

        self.assertFalse('mailingtempqueue' in self.db_sync.collection_names())