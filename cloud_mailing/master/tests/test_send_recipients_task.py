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
import logging
import random
import time
from datetime import datetime

from bson import DBRef
from twisted.internet import defer
from twisted.trial import unittest

from cloud_mailing.master import settings_vars
from cloud_mailing.master.db_initialization import init_master_db
from cloud_mailing.master.models import MAILING_STATUS
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
        factories.CloudClientFactory(paired=True, serial="UT")
        factories.RecipientFactory()
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

    @defer.inlineCallbacks
    def test_recipients_sort(self):
        factories.CloudClientFactory(paired=True, serial="UT")
        mailing = factories.MailingFactory(status=MAILING_STATUS.READY, total_recipient=2, total_pending=2)
        factories.RecipientFactory(email="1@dom.com", mailing=mailing)
        factories.RecipientFactory(email="2@dom.com", mailing=mailing, next_try=datetime(2000, 1, 1))

        my_task = SendRecipientsTask.getInstance()
        recipients = yield my_task._get_recipients(1, "UT")

        self.assertEqual(1, len(recipients))
        self.assertEqual("2@dom.com", recipients[0]['email'])

    @defer.inlineCallbacks
    def test_nb_max_recipients_should_never_be_zero(self):
        factories.CloudClientFactory(paired=True, serial="UT")
        mailing1 = factories.MailingFactory(status=MAILING_STATUS.READY, total_recipient=1, total_pending=1)
        mailing2 = factories.MailingFactory(status=MAILING_STATUS.READY, total_recipient=1, total_pending=1)
        factories.RecipientFactory(email="1@dom.com", mailing=mailing1)
        factories.RecipientFactory(email="2@dom.com", mailing=mailing2)

        my_task = SendRecipientsTask.getInstance()
        recipients = yield my_task._get_recipients(1, "UT")

        self.assertEqual(1, len(recipients))


class SendRecipientsPerfsTestCase(DatabaseMixin, unittest.TestCase):
    def setUp(self):
        # logging.basicConfig(level=logging.DEBUG)
        # logging.getLogger('factory').setLevel(logging.INFO)
        self.connect_to_db()
        init_master_db(self.db_sync)


    def tearDown(self):
        self.disconnect_from_db()

    @defer.inlineCallbacks
    def test_perfs(self):
        factories.CloudClientFactory(paired=True, serial="UT")
        # print "Filling db...",
        t0 = time.time()
        mailing_ids = []
        for i in range(10):
            ml = factories.MailingFactory(status=MAILING_STATUS.READY)
            mailing_ids.append(ml.id)
        self.db_sync.mailingrecipient.insert_many(
            [{
                 "next_try": datetime.utcnow(),
                 "in_progress": False,
                 "mailing": DBRef("mailing", random.choice(mailing_ids)),
                 "contact": {
                     "attachments": [
                     ],
                     "firstname": "John",
                     "gender": "M",
                     "email": "john.doe%d@cloud-mailing.net" % i,
                     "lastname": "DOE",
                     "id": i
                 },
                 "tracking_id": "e6992614-90ad-422b-8827-%d" % i,
                 "send_status": "READY",
                 "email": "john.doe%d@cloud-mailing.net" % i,
                 "doamin_name": "cloud-mailing.net",
             } for i in range(10000)])

        results = yield self.db.mailingrecipient.aggregate([
            {'$group': {'_id': '$mailing', 'sum': {'$sum': 1}}}
        ])
        for result in results:
            yield self.db.mailing.update({'_id': result['_id'].id}, {'$set': {'total_recipient': result['sum'], 'total_pending': result['sum']}})

        # self.db_sync.mailing.insert_many(self.db_sync['_mailing.perfs'].find())
        # self.db_sync.mailingrecipient.insert_many(self.db_sync['_mailingrecipient.perfs'].find(limit=100000))

        # print "done in %.1f seconds." % (time.time() - t0)
        # print "Running test...",
        t0 = time.time()
        my_task = SendRecipientsTask.getInstance()
        recipients = yield my_task._get_recipients(1000, "UT")
        # print "done in %.1f seconds." % (time.time() - t0)

        self.assertEqual(1000, len(recipients))
