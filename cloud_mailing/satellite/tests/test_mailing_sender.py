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

from ...common.unittest_mixins import DatabaseMixin
from ..mail_customizer import MailCustomizer
from ..mailing_sender import MailingSender
from ..models import MailingRecipient, Mailing
from twisted.trial.unittest import TestCase
from . import factories
import os
import email.parser
import email.message
import base64

__author__ = 'ricard'

class TestMailingSender(DatabaseMixin, TestCase):
    def setUp(self):
        self.connect_to_db()

    def tearDown(self):
        self.disconnect_from_db()

    def test_recipients_selection(self):
        ml = factories.MailingFactory()
        factories.RecipientFactory(mailing=ml)
        factories.RecipientFactory(mailing=ml)
        factories.RecipientFactory(mailing=ml)
        factories.RecipientFactory(mailing=ml)
        filter = MailingSender.make_queue_filter()
        self.assertEqual(4, MailingRecipient.find(filter).count())
