#!/usr/bin/env python
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

# encoding: utf-8
from ConfigParser import RawConfigParser
import httplib
import random
import ssl
from subprocess import PIPE, Popen
import urllib2
import xmlrpclib
import unittest
import time, os
import base64
import sys


class Config(RawConfigParser):
    def get(self, section, option, default = None):
        if self.has_option(section, option) or default is None:
            return RawConfigParser.get(self, section, option)
        else:
            return default

    def getint(self, section, option, default = None):
        if self.has_option(section, option) or not isinstance(default, int):
            return RawConfigParser.getint(self, section, option)
        else:
            return default

    def getboolean(self, section, option, default = None):
        if self.has_option(section, option) or not isinstance(default, bool):
            return RawConfigParser.getboolean(self, section, option)
        else:
            return default


test_config = Config()
if os.path.exists("test_config.ini"):
    test_config.read("test_config.ini")


def load_config(target_name='TARGET'):
    return {'ip': test_config.get(target_name, "ip", "127.0.0.1"),
            'smtp_port': test_config.getint(target_name, "smtp_port", 25),
            'pop_port': test_config.getint(target_name, "pop_port", 110),
            'admin_pwd': test_config.get(target_name, "admin_pwd", "password"),
            'api_key': urllib2.quote(test_config.get(target_name, "api_key", "the_api_key")),
            'admin_password': test_config.get(target_name, "admin_password", "password"),
            }


CONFIG = load_config()

# Set it to true if network isn't available and if DNS and SMTP are faked
OFFLINE_TESTS=True
PURGE_OLD_MAILING = test_config.getboolean("SETTINGS", "purge_old_tests", True)

TOTAL_RECIPIENTS_FOR_BIG_MAILING = test_config.getint("SETTINGS", "total_recipients_for_big_mailing", 100000)

domains = (
    'free.fr',
    'orange.fr',
    'google.com',
    'wanadoo.fr',
    'akema.fr',
    'calexium.com',
    'yahoo.com',
    'live.com',
    'laposte.net',
    'apple.com',
    'mailfountain.net',
    'akemail.fr',
    'ma-societe.fr',
    'my-company.biz',
)



class CloudMailingsTestCase(unittest.TestCase):
    def setUp(self):
        self.domain_name = "unittest.cloud-mailing.net"
        self.cloudMailingsRpc = xmlrpclib.ServerProxy("https://admin:%(api_key)s@%(ip)s:33610/CloudMailing" % CONFIG,
                                                      context=ssl._create_unverified_context())
        if PURGE_OLD_MAILING:
            print "DELETING ALL PREVIOUS MAILING..."
            self.cloudMailingsRpc.delete_all_mailings_for_domain(self.domain_name)

    def tearDown(self):
        pass

    def _check_domain_sender(self, email_filename):
        import email.parser

        m_parser = email.parser.Parser()
        with file(email_filename, 'rt') as fp:
            message = m_parser.parse(fp)
        import email.utils

        domain_name2 = email.utils.getaddresses([message['From']])[0][1].split('@')[1]
        self.assertEquals(domain_name2, self.domain_name) # security to only test on UT domain

    def _get_memory_for_process(self, proc_name):
        for line in Popen(["ps", "-mA", "-o", "rss,command=CMD"], stdout=PIPE).communicate()[0].splitlines():
            if proc_name in line:
                return int(line.split()[0])

    def _make_recipients_list(self, count):
        domains = (
            'free.fr',
            'orange.fr',
            'google.com',
            'wanadoo.fr',
            'akema.fr',
            'calexium.com',
            'yahoo.com',
            'live.com',
            'laposte.net',
            'apple.com',
            'mailfountain.net',
            #'akemail.fr',
            'ma-societe.fr',
            'my-company.biz',
        )
        return [{'email': "email%d@%s" % (i, domains[random.randint(0, len(domains)-1)])} for i in range(count)]

    def test_get_mailings(self):
        self.assertTrue(isinstance(self.cloudMailingsRpc.list_mailings(self.domain_name), (list, tuple)))

    def test_create_mailing(self):
        mailing_count = len(self.cloudMailingsRpc.list_mailings(self.domain_name))
        self.assertGreaterEqual(mailing_count, 0)
        mailing_id = self.cloudMailingsRpc.create_mailing("my-mailing@%s" % self.domain_name, "My Mailing",
                                                       'The great newsletter',
                                                       "<h1>Title</h1><p>Coucou</p>", "Title\nCoucou\n", "UTF-8")
        self.assertGreater(mailing_id, 0)
        mailings = self.cloudMailingsRpc.list_mailings(self.domain_name)
        self.assertEquals(len(mailings), mailing_count + 1)
        mail_from = "my-mailing@%s" % self.domain_name
        self.assertEquals(mailings[-1]['id'], mailing_id)
        self.assertEquals(mailings[-1]['mail_from'], mail_from)
        recipients_list = [{'email': "cedric.ricard@orange.fr"},
                           {'email': "ricard@free.fr"},
                           {'email': "ricard@calexium.com"},
                           {'email': "cedric.ricard@calexium.com"},
                           {'email': "cant_exist_email_for_error@calexium.com"},
                           {'email': "cedric@verybaddomainsisijesuissur.com"},
                           ]
        results = self.cloudMailingsRpc.add_recipients(mailing_id, recipients_list)
        for r1, r2 in zip(recipients_list, results):
            self.assertDictContainsSubset({'email': r1['email']}, r2)
            self.assertNotIn('error', r2)

        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        self.assertEqual(mailing['id'], mailing_id)
        self.assertEqual(mailing['total_recipient'], 6)


        # 2nd mailing
        email_filename = os.path.join('data', 'email.rfc822')
        self._check_domain_sender(email_filename)

        mailing2_id = self.cloudMailingsRpc.create_mailing_ext(base64.b64encode(file(email_filename, 'rt').read()))
        self.assertGreater(mailing2_id, 0)
        self.assertEquals(len(self.cloudMailingsRpc.list_mailings(self.domain_name)), mailing_count + 2)
        mailing = self.cloudMailingsRpc.list_mailings()[-1]
        # self.assertEqual(mailing['id'], mailing2_id)
        # self.assertEqual(mailing['domain_name'], self.domain_name)
        # self.assertEqual(mailing['total_recipient'], 0)

    def test_run_mailing(self):
        mailing_count = len(self.cloudMailingsRpc.list_mailings(self.domain_name))
        email_filename = os.path.join('data', 'email.rfc822')
        dkim_private_key = open(os.path.join('data', 'unittest.cloud-mailing.net', 'mail.private'), 'rt').read()
        self._check_domain_sender(email_filename)
        mail_from = "my-mailing@%s" % self.domain_name
        mailing_id = self.cloudMailingsRpc.create_mailing_ext(base64.b64encode(file(email_filename, 'rt').read()))
        self.assertGreater(mailing_id, 0)
        mailings = self.cloudMailingsRpc.list_mailings(self.domain_name)
        self.assertEquals(len(mailings), mailing_count + 1)
        self.assertEquals(mailings[-1]['mail_from'], mail_from)
        recipients_list = [{'email': "cedric.ricard@orange.fr"},
                           {'email': "ricard@free.fr"},
                           {'email': "ricard33+cm@gmail.com"},
                           {'email': "ricard@calexium.com"},
                           {'email': "cedric.ricard@calexium.com"},
                           {'email': "cant_exist_email_for_error@calexium.com"},
                           {'email': "cedric@verybaddomainsisijesuissur.com"},
                           ]
        results = self.cloudMailingsRpc.add_recipients(mailing_id, recipients_list)
        for r1, r2 in zip(recipients_list, results):
            self.assertDictContainsSubset({'email': r1['email']}, r2)
            self.assertNotIn('error', r2)
        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        self.assertEqual(mailing['total_recipient'], 7)
        self.cloudMailingsRpc.set_mailing_properties(mailing_id, {'scheduled_duration': 3, 'testing': False,
                                                                  'dkim': {
                                                                      'selector': 'mail',
                                                                      'domain': self.domain_name,
                                                                      'privkey': dkim_private_key
                                                                  }},)

        self.cloudMailingsRpc.start_mailing(mailing_id)
        self.cloudMailingsRpc.mailing_manager_force_check()
        self.cloudMailingsRpc.update_statistics()
        mailings = self.cloudMailingsRpc.list_mailings(self.domain_name)
        mailing = mailings[-1]
        t0 = time.time()
        while mailing['total_pending'] > 0:
            self.assertTrue(mailing['status'] in ('READY', 'RUNNING'))
            self.assertLess(time.time() - t0, 120) # 2 minutes max
            self.cloudMailingsRpc.mailing_manager_force_check()
            time.sleep(2)
            mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        # stats not up to date
        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        #self.assertEqual(mailing['status'], 'FINISHED')
        #print repr(mailing)
        self.assertEqual(mailing['total_recipient'], 7)
        self.assertEqual(mailing['total_pending'], 0)
        self.assertEqual(mailing['total_sent'], 5)
        self.assertEqual(mailing['total_error'], 2)

    def test_send_test_emails(self):
        mailing_count = len(self.cloudMailingsRpc.list_mailings(self.domain_name))
        email_filename = os.path.join('data', 'email.rfc822')
        self._check_domain_sender(email_filename)
        mail_from = "my-mailing@%s" % self.domain_name
        mailing_id = self.cloudMailingsRpc.create_mailing_ext(base64.b64encode(file(email_filename, 'rt').read()))
        self.assertGreater(mailing_id, 0)
        self.cloudMailingsRpc.set_mailing_properties(mailing_id, {'testing': True})
        recipients_list = [{'email': "cedric.ricard@orange.fr"},
                           {'email': "ricard@free.fr"},
                           ]
        results = self.cloudMailingsRpc.send_test(mailing_id, recipients_list)
        for r1, r2 in zip(recipients_list, results):
            self.assertDictContainsSubset({'email': r1['email']}, r2)
            self.assertNotIn('error', r2)
        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        self.assertEqual(mailing['total_recipient'], 2)

        t0 = time.time()
        while mailing['total_pending'] > 1:   # the unknown domain will take more time...
            self.assertEqual(mailing['status'], 'FILLING_RECIPIENTS')
            self.assertLess(time.time() - t0, 30) # 30 seconds max
            # self.cloudMailingsRpc.mailing_manager_force_check()
            time.sleep(2)
            mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        # stats not up to date
        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        self.assertEqual(mailing['status'], 'FILLING_RECIPIENTS')
        #print repr(mailing)
        self.assertEqual(mailing['total_recipient'], 2)
        self.assertEqual(mailing['total_sent'], 2)
        self.assertEqual(mailing['total_error'], 0)

    def test_memory_consumption(self):
        """
        Test that should be run locally only, due to memory check.
        """
        start_memory = self._get_memory_for_process('cm_satellite')
        self.assertIsNotNone(start_memory, "Can't get memory information")
        max_delta_memory = 50000
        mailing_count = len(self.cloudMailingsRpc.list_mailings(self.domain_name))
        email_filename = os.path.join('data', 'medium_sized.rfc822')
        self._check_domain_sender(email_filename)
        mail_from = "my-mailing@%s" % self.domain_name
        mailing_id = self.cloudMailingsRpc.create_mailing_ext(base64.b64encode(file(email_filename, 'rt').read()))
        self.assertGreater(mailing_id, 0)
        mailings = self.cloudMailingsRpc.list_mailings(self.domain_name)
        self.assertEquals(len(mailings), mailing_count + 1)
        self.assertEquals(mailings[-1]['mail_from'], mail_from)
        recipients_list = self._make_recipients_list(100)
        results = self.cloudMailingsRpc.add_recipients(mailing_id, recipients_list)
        for r1, r2 in zip(recipients_list, results):
            self.assertDictContainsSubset({'email': r1['email']}, r2)
            self.assertNotIn('error', r2)
        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        self.assertEqual(mailing['total_recipient'], len(recipients_list))
        self.cloudMailingsRpc.set_mailing_properties(mailing_id, {'scheduled_duration': 300, 'testing': True})

        self.cloudMailingsRpc.start_mailing(mailing_id)
        self.cloudMailingsRpc.mailing_manager_force_check()
        mailings = self.cloudMailingsRpc.list_mailings(self.domain_name)
        mailing = mailings[-1]
        t0 = time.time()
        while mailing['status'] != 'FINISHED':
            self.assertTrue(mailing['status'] in ('READY', 'RUNNING'))
            self.assertLess(time.time() - t0, 300) # 1 minutes max
            self.cloudMailingsRpc.mailing_manager_force_check()
            time.sleep(2)
            mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
            memory = self._get_memory_for_process('cm_satellite')
            self.assertLess(memory, start_memory + max_delta_memory)
        self.cloudMailingsRpc.mailing_manager_force_check()
        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        self.assertEqual(mailing['status'], 'FINISHED')
        #print repr(mailing)
        self.assertEqual(mailing['total_recipient'], len(recipients_list))
        self.assertEqual(mailing['total_pending'], 0)
        #self.assertEqual(mailing['total_sent'], 4)
        #self.assertEqual(mailing['total_error'], 2)

    def _generate_recipients_list(self, count):
        global domains
        for i in range(count):
            d = {'n': i, 'n10': i / 10, 'n100': i / 100, 'n1000': i / 1000,
                 'domain': domains[random.randint(0, len(domains) - 1)]}
            recipient = {
                'email': 'email%(n)d@%(domain)s' % d,
                'first_name': 'Firstname%(n)d' % d,
                'last_name': 'Lastname%(n)d' % d,
                'company': 'The company',
                'comment': 'Free \n multiline text %(n)d.' % d
            }

            yield recipient

    # @unittest.skip("Too long. Should be run manually.")
    def test_run_big_mailings(self):
        nb_mailings = test_config.getint("SETTINGS", "total_mailings", 10)
        all_mailings = []
        total_recipients = 0

        for i in range(nb_mailings):
            mailing_id, nb_recipients = self._create_mailing()
            all_mailings.append(mailing_id)
            total_recipients += nb_recipients

        # self.cloudMailingsRpc.mailing_manager_force_check()
        #time.sleep(6)
        mailings = self.cloudMailingsRpc.list_mailings({'id': all_mailings})
        t0 = time.time()
        while sum(map(lambda mailing: mailing['total_pending'], mailings)) > 0:
            for mailing in mailings:
                self.assertTrue(mailing['status'] in ('READY', 'RUNNING', 'FINISHED'))
            self.assertLess(time.time() - t0, 86400) # 1 day max
            # self.cloudMailingsRpc.mailing_manager_force_check()
            time.sleep(10)
            # self.cloudMailingsRpc.update_statistics()
            mailings = self.cloudMailingsRpc.list_mailings({'id': all_mailings})
        # stats not up to date
        # self.cloudMailingsRpc.update_statistics()
        mailings = self.cloudMailingsRpc.list_mailings({'id': all_mailings})
        #self.assertEqual(mailing['status'], 'FINISHED')
        #print repr(mailing)
        self.assertEqual(sum(map(lambda mailing: mailing['total_recipient'], mailings)), total_recipients)
        self.assertEqual(sum(map(lambda mailing: mailing['total_pending'], mailings)), 0)
        self.assertEqual(sum(map(lambda mailing: mailing['total_sent'], mailings)), total_recipients)
        self.assertEqual(sum(map(lambda mailing: mailing['total_error'], mailings)), 0)

    def _create_mailing(self):
        mailing_count = len(self.cloudMailingsRpc.list_mailings(self.domain_name))
        email_filename = os.path.join('data', 'email.rfc822')
        self._check_domain_sender(email_filename)
        mail_from = "my-mailing@%s" % self.domain_name
        mailing_id = self.cloudMailingsRpc.create_mailing_ext(base64.b64encode(file(email_filename, 'rt').read()))
        self.assertGreater(mailing_id, 0)
        mailings = self.cloudMailingsRpc.list_mailings(self.domain_name)
        self.assertEquals(len(mailings), mailing_count + 1)
        self.assertEquals(mailings[-1]['mail_from'], mail_from)
        self.cloudMailingsRpc.set_mailing_properties(mailing_id, {'scheduled_duration': 1440, 'testing': True,
                                                                  'dont_close_if_empty': True})
        self.cloudMailingsRpc.start_mailing(mailing_id)
        total_recipients = TOTAL_RECIPIENTS_FOR_BIG_MAILING
        recipients_list = self._generate_recipients_list(total_recipients)
        rcpts_list2 = []

        def _add_recipients(rcpts_list):
            results = self.cloudMailingsRpc.add_recipients(mailing_id, rcpts_list)
            for r1, r2 in zip(rcpts_list, results):
                self.assertDictContainsSubset({'email': r1['email']}, r2)
                self.assertNotIn('error', r2)

        count = 0
        for recipient in recipients_list:
            rcpts_list2.append(recipient)
            if len(rcpts_list2) >= 1000:
                _add_recipients(rcpts_list2)
                count += len(rcpts_list2)
                print("Sent %d recipients over %d" % (count, total_recipients))
                rcpts_list2 = []
        if len(rcpts_list2):
            _add_recipients(rcpts_list2)
        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        self.assertEqual(mailing['total_recipient'], total_recipients)
        self.cloudMailingsRpc.set_mailing_properties(mailing_id, {'dont_close_if_empty': False})
        return mailing_id, total_recipients

    def test_get_full_reports_with_email_content(self):
        mailing_count = len(self.cloudMailingsRpc.list_mailings(self.domain_name))
        email_filename = os.path.join('data', 'email.rfc822')
        self._check_domain_sender(email_filename)
        mail_from = "my-mailing@%s" % self.domain_name
        mailing_id = self.cloudMailingsRpc.create_mailing_ext(base64.b64encode(file(email_filename, 'rt').read()))
        self.assertGreater(mailing_id, 0)
        self.cloudMailingsRpc.set_mailing_properties(mailing_id, {'testing': True, 'backup_customized_emails': True})
        recipients_list = [{'email': "cedric.ricard@orange.fr", 'firstname': 'Cedric', 'lastname': 'RICARD'},
                           {'email': "ricard@free.fr", 'firstname': 'John', 'lastname': 'DOE'},
                           ]
        results = self.cloudMailingsRpc.send_test(mailing_id, recipients_list)
        for r1, r2 in zip(recipients_list, results):
            self.assertDictContainsSubset({'email': r1['email']}, r2)
            self.assertNotIn('error', r2)
        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        self.assertEqual(mailing['total_recipient'], 2)

        mailing = self.cloudMailingsRpc.list_mailings(self.domain_name)[-1]
        t0 = time.time()
        recipients_status = {}
        cursor = ''
        while len(recipients_status) < len(recipients_list):   # the unknown domain will take more time...
            # self.assertEqual(mailing['status'], 'FILLING_RECIPIENTS')
            self.assertLess(time.time() - t0, 60) # 60 seconds max
            results = self.cloudMailingsRpc.get_recipients_status_updated_since(cursor, {'mailings': [mailing['id']]})
            cursor = results['cursor']
            recipients = results['recipients']
            for recipient in recipients:
                recipients_status[recipient['email']] = recipient
            time.sleep(2)
        self.assertEqual(recipients_status['cedric.ricard@orange.fr']['status'], 'FINISHED')
        self.assertEqual(recipients_status['ricard@free.fr']['status'], 'FINISHED')
        self.assertIn('*Bonjour*Cedric RICARD', recipients_status['cedric.ricard@orange.fr']['customized_content'])
        self.assertIn('*Bonjour*John DOE', recipients_status['ricard@free.fr']['customized_content'])


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Runs acceptance tests for CloudMailing')
    # parser.add_argument('test_fixture', type=str, nargs='?',
    #                     help='An optional fixture name')
    parser.add_argument('--ip', dest='ip', default=None,
                        help='IP address of the CloudMailing (default: 127.0.0.1)')
    parser.add_argument('--target', dest='target', default=None,
                        help='Target name (used as section name in configuration file)')

    args, argv = parser.parse_known_args()
    if args.target:
        CONFIG = load_config(args.target)
    if args.ip:
        CONFIG['ip'] = args.ip

    argv.insert(0, sys.argv[0])
    unittest.main(argv=argv)
