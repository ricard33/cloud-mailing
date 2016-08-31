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

import base64
import json
from cookielib import CookieJar

from twisted.internet import reactor
from twisted.web import resource, server
from twisted.web.guard import BasicCredentialFactory, DigestCredentialFactory
from twisted.web.client import readBody, Agent, CookieAgent
from twisted.web.http_headers import Headers

from ...common import http_status
from ...common.api_common import AuthenticatedSite
from ...common.unittest_mixins import JsonProducer
from ..api_authentication import AdminChecker
from ..rest_api import make_rest_api

__author__ = 'Cedric RICARD'


class UTSession(server.Session):
    def startCheckingExpiration(self):
        # disable expire() callback due to "Reactor was unclean" problem during unittests
        pass

class RestApiTestMixin(object):

    def start_rest_api(self):
        root_page = resource.Resource()
        root_page.putChild('api', make_rest_api())
        site = AuthenticatedSite(root_page)
        site.credentialFactories = [BasicCredentialFactory("CloudMailing API"), DigestCredentialFactory("md5", "CloudMailing API")]
        site.credentialsCheckers = [AdminChecker()]
        site.sessionFactory = UTSession
        self.p = reactor.listenTCP(0, site,
                                    interface="127.0.0.1")
        self.port = self.p.getHost().port
        self.api_base_url = 'http://127.0.0.1:%d/api/' % self.port
        self.agent = None

    def stop_rest_api(self):
        return self.p.stopListening()
        self.agent = None


    def log(self, msg):
        print msg
        return msg

    @staticmethod
    def cb_decode_json(body):
        return json.loads(body)

    def call_api(self, verb, url, expected_status_code=http_status.HTTP_200_OK, headers=None, data=None,
                 pre_read_body_cb=None, credentials=None):
        def cbResponse(response):
            # print 'Response version:', response.version
            # print 'Response code:', response.code
            # print 'Response phrase:', response.phrase
            # print 'Response headers:'
            # print pformat(list(response.headers.getAllRawHeaders()))
            if expected_status_code:
                self.assertEqual(expected_status_code, response.code, "Bad result code for request '%s %s'" % (verb, url))
            return response

        def cb_load_body(response):
            d = readBody(response)
            if response.code != http_status.HTTP_204_NO_CONTENT:
                d.addCallback(RestApiTestMixin.cb_decode_json)
            return d

        _headers = {'User-Agent': ['Twisted Web Client Example']}
        if credentials is not None:
            _headers['authorization'] = ['basic %s' % base64.encodestring('%s:%s' % credentials)]
        if headers:
            _headers.update(headers)
        if self.agent is None:
            self.agent = CookieAgent(Agent(reactor), CookieJar())
        body = None
        if data is not None:
            body = JsonProducer(data)
        d = self.agent.request(verb,
                          self.api_base_url + url,
                          Headers(_headers),
                          body)
        d.addCallback(cbResponse)
        if pre_read_body_cb:
            d.addCallback(pre_read_body_cb)
        d.addCallback(cb_load_body)
        return d