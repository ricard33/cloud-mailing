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

from ...common.unittest_mixins import DatabaseMixin
from ..mail_customizer import MailCustomizer
from ..models import MailingRecipient, Mailing, DomainStats, HourlyStats
from twisted.trial.unittest import TestCase
import factories
import os
import email.parser
import email.message
import base64

__author__ = 'ricard'


class TestHourlyStats(DatabaseMixin, TestCase):
    def setUp(self):
        self.connect_to_db()

    def tearDown(self):
        self.disconnect_from_db()

    def test_add_sent(self):
        HourlyStats.add_sent()
        self.assertEqual(1, HourlyStats.find_one().sent)
        self.assertEqual(1, HourlyStats.find_one().tries)
        self.assertEqual(0, HourlyStats.find_one().failed)
        self.assertEqual(False, HourlyStats.find_one().up_to_date)
        self.assertEqual(0, HourlyStats.find_one().date.minute)
        self.assertEqual(0, HourlyStats.find_one().date.second)
        self.assertEqual(0, HourlyStats.find_one().date.microsecond)
        HourlyStats.update({}, {'$set': {'up_to_date': True}}, multi=True)
        self.assertEqual(True, HourlyStats.find_one().up_to_date)
        HourlyStats.add_sent()
        self.assertEqual(2, HourlyStats.find_one().sent)
        self.assertEqual(2, HourlyStats.find_one().tries)
        self.assertEqual(0, HourlyStats.find_one().failed)
        self.assertEqual(False, HourlyStats.find_one().up_to_date)

    def test_add_failed(self):
        HourlyStats.add_failed()
        self.assertEqual(0, HourlyStats.find_one().sent)
        self.assertEqual(1, HourlyStats.find_one().tries)
        self.assertEqual(1, HourlyStats.find_one().failed)

    def test_add_try(self):
        HourlyStats.add_try()
        self.assertEqual(0, HourlyStats.find_one().sent)
        self.assertEqual(1, HourlyStats.find_one().tries)
        self.assertEqual(0, HourlyStats.find_one().failed)


class TestDomainStats(DatabaseMixin, TestCase):
    def setUp(self):
        self.connect_to_db()

    def tearDown(self):
        self.disconnect_from_db()

    def test_add_sent(self):
        DomainStats.add_sent("example.org")
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).sent)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).tries)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).failed)
        DomainStats.add_sent("example.org")
        self.assertEqual(2, DomainStats.find_one({'domain_name': 'example.org'}).sent)
        self.assertEqual(2, DomainStats.find_one({'domain_name': 'example.org'}).tries)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).failed)

    def test_add_failed(self):
        DomainStats.add_failed("example.org")
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).sent)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).tries)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).failed)

    def test_add_try(self):
        DomainStats.add_try("example.org")
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).sent)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).tries)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).failed)

    def test_add_dns_success(self):
        DomainStats.add_dns_success("example.org")
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).tries)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).dns_tries)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_temp_errors)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_fatal_errors)
        self.assertEqual(None, DomainStats.find_one({'domain_name': 'example.org'}).dns_last_error)

    def test_add_dns_temp_error(self):
        DomainStats.add_dns_temp_error("example.org", Exception('test'))
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).tries)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).dns_tries)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).dns_temp_errors)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).dns_cumulative_temp_errors)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_fatal_errors)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_cumulative_fatal_errors)
        self.assertEqual('exceptions.Exception', DomainStats.find_one({'domain_name': 'example.org'}).dns_last_error)

        DomainStats.add_dns_success("example.org")
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).tries)
        self.assertEqual(2, DomainStats.find_one({'domain_name': 'example.org'}).dns_tries)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_temp_errors)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).dns_cumulative_temp_errors)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_fatal_errors)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_cumulative_fatal_errors)
        self.assertEqual(None, DomainStats.find_one({'domain_name': 'example.org'}).dns_last_error)

    def test_add_dns_fatal_error(self):
        DomainStats.add_dns_fatal_error("example.org", Exception('test'))
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).tries)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).dns_tries)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_temp_errors)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_cumulative_temp_errors)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).dns_fatal_errors)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).dns_cumulative_fatal_errors)
        self.assertEqual('exceptions.Exception', DomainStats.find_one({'domain_name': 'example.org'}).dns_last_error)

        DomainStats.add_dns_success("example.org")
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).tries)
        self.assertEqual(2, DomainStats.find_one({'domain_name': 'example.org'}).dns_tries)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_temp_errors)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_cumulative_temp_errors)
        self.assertEqual(0, DomainStats.find_one({'domain_name': 'example.org'}).dns_fatal_errors)
        self.assertEqual(1, DomainStats.find_one({'domain_name': 'example.org'}).dns_cumulative_fatal_errors)
        self.assertEqual(None, DomainStats.find_one({'domain_name': 'example.org'}).dns_last_error)

