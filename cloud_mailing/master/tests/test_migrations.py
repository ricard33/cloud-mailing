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
from twisted.trial import unittest

from cloud_mailing.common.unittest_mixins import DatabaseMixin
from cloud_mailing.master.db_initialization import do_migrations, init_master_db, migrations

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
