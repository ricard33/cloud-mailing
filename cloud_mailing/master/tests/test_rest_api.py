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
from pprint import pformat
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from twisted.web import resource, http, static
from cloud_mailing.master.rest_api import RestApiHome, make_rest_api

__author__ = 'Cedric RICARD'

import os
import json

from twisted.internet import reactor
from twisted.trial.unittest import TestCase
from twisted.web import server, xmlrpc

from ...common.unittest_mixins import DatabaseMixin
from ...common.models import Settings
from ..xmlrpc_api import CloudMailingRpc
from ...common import settings
from ...common.config_file import ConfigFile


def cb_decode_json(body):
    return json.loads(body)

class HomeTestCase(DatabaseMixin, TestCase):

    def setUp(self):
        self.connect_to_db()
        self.__proxy = None
        root_page = resource.Resource()
        root_page.putChild('api', make_rest_api())
        self.p = reactor.listenTCP(0, server.Site(root_page),
                                    interface="127.0.0.1")
        self.port = self.p.getHost().port
        self.api_base_url = 'http://127.0.0.1:%d/api/' % self.port
        Settings.set('TEST_MODE', True)
        config = ConfigFile()
        config.read(settings.CONFIG_FILE)

        config.set('CM_MASTER', 'API_KEY', 'the_API_key')
        if not os.path.exists(settings.CONFIG_PATH):
            os.makedirs(settings.CONFIG_PATH)
        with open(settings.CONFIG_FILE, 'wt') as fp:
            config.write(fp)

    def tearDown(self):
        if os.path.exists(settings.CONFIG_FILE):
            os.remove(settings.CONFIG_FILE)
        self.__proxy = None
        return self.p.stopListening().addBoth(lambda x: self.disconnect_from_db())

    def log(self, msg):
        print msg

    def test_get_version(self):
        agent = Agent(reactor)

        def cbResponse(response):
            # print 'Response version:', response.version
            # print 'Response code:', response.code
            # print 'Response phrase:', response.phrase
            # print 'Response headers:'
            # print pformat(list(response.headers.getAllRawHeaders()))
            d = readBody(response)
            d.addCallback(cb_decode_json)
            d.addCallback(cbBody)
            return d

        def cbBody(body):
            # print body
            self.assertEqual("CloudMailing", body['product_name'])

        d = agent.request(
            'GET',
            self.api_base_url,
            Headers({'User-Agent': ['Twisted Web Client Example']}),
            None)

        d.addCallback(cbResponse)

        return d
