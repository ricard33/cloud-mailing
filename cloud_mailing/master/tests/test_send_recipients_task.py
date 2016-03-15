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
from twisted.internet import defer
from twisted.trial import unittest

from cloud_mailing.master import settings_vars
from cloud_mailing.master.send_recipients_task import SendRecipientsTask
from cloud_mailing.master.tests import factories
from ...common.unittest_mixins import DatabaseMixin


class SendRecipientsTaskTestCase(DatabaseMixin, unittest.TestCase):

    def setUp(self):
        self.connect_to_db()

    def tearDown(self):
        self.disconnect_from_db()

    @defer.inlineCallbacks
    def test_run(self):
        client = factories.CloudClientFactory(paired=True, serial="UT")
        factories.MailingTempQueueFactory(client=client)
        settings_vars.set(settings_vars.SATELLITE_MAX_RECIPIENTS_TO_SEND, 555)
        class MyStubTask(SendRecipientsTask):
            def __init__(self, testcase):
                super(MyStubTask, self).__init__()
                self.count = 0
                self.test = testcase

            def _send_recipients_to_satellite(self, serial, count):
                self.count += 1
                self.test.assertEqual("UT", serial)
                self.test.assertEqual(555, count)

        my_task = MyStubTask.getInstance(self)
        yield my_task.run()
        self.assertEqual(1, my_task.count)


