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
import json
import os

from mogo import connect
from mogo.connection import Connection
from . import settings
from twisted.internet import reactor
from twisted.web import server, resource
from twisted.web.client import readBody, Agent
from twisted.web.http_headers import Headers
from cloud_mailing.common.config_file import ConfigFile
from cloud_mailing.common.models import Settings
from cloud_mailing.master.rest_api import make_rest_api

__author__ = 'ricard'


class CommonTestMixin(object):
    def setup_settings(self):
        Settings.set('TEST_MODE', True)
        config = ConfigFile()
        config.read(settings.CONFIG_FILE)

        config.set('CM_MASTER', 'API_KEY', 'the_API_key')
        if not os.path.exists(settings.CONFIG_PATH):
            os.makedirs(settings.CONFIG_PATH)
        with open(settings.CONFIG_FILE, 'wt') as fp:
            config.write(fp)

    def clear_settings(self):
        if os.path.exists(settings.CONFIG_FILE):
            os.remove(settings.CONFIG_FILE)


class DatabaseMixin(object):
    def connect_to_db(self):
        self.db_conn = connect(settings.TEST_DATABASE)
        # self.db_conn.drop_database(settings.TEST_DATABASE)
        db = Connection.instance().get_database()
        for col in db.collection_names(include_system_collections=False):
            db.drop_collection(col)

    def disconnect_from_db(self):
        self.db_conn.disconnect()


class RestApiTestMixin(object):

    def start_rest_api(self):
        root_page = resource.Resource()
        root_page.putChild('api', make_rest_api())
        self.p = reactor.listenTCP(0, server.Site(root_page),
                                    interface="127.0.0.1")
        self.port = self.p.getHost().port
        self.api_base_url = 'http://127.0.0.1:%d/api/' % self.port

    def stop_rest_api(self):
        return self.p.stopListening()

    def log(self, msg):
        print msg

    @staticmethod
    def cb_decode_json(body):
        return json.loads(body)

    def call_api(self, verb, url, expected_status_code, headers=None, body=None):
        def cbResponse(response):
            # print 'Response version:', response.version
            # print 'Response code:', response.code
            # print 'Response phrase:', response.phrase
            # print 'Response headers:'
            # print pformat(list(response.headers.getAllRawHeaders()))
            if expected_status_code:
                self.assertEqual(expected_status_code, response.code)
            d = readBody(response)
            d.addCallback(RestApiTestMixin.cb_decode_json)
            return d

        _headers = {'User-Agent': ['Twisted Web Client Example']}
        if headers:
            _headers.update(headers)
        agent = Agent(reactor)
        d = agent.request(verb,
                          self.api_base_url + url,
                          Headers(_headers),
                          body)
        d.addCallback(cbResponse)
        return d
