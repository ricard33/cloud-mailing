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
import json
import platform
import re
from datetime import datetime

from twisted.cred import credentials
from twisted.python.components import registerAdapter
from twisted.web import server
from twisted.web.resource import Resource
from twisted.web.server import Session
from twisted.web.xmlrpc import Proxy

from .satellites import ListSatellitesApi
from .mailings import ListMailingsApi
from .recipients import ListRecipientsApi
from .. import serializers
from ..api_common import log_security
from ... import __version__
from ...common import http_status
from ...common import settings
from ...common.api_common import ICurrentUser
from ...common.json_tools import json_default
from ...common.permissions import AllowAny, IsAdminUser, IsAuthenticated
from ...common.rest_api_common import ApiResource, log, CurrentUser

__author__ = 'Cedric RICARD'

API_VERSION = 1
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
date_re = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def datetime_parser(dct):
    for k, v in dct.items():
        if isinstance(v, basestring) and date_re.search(v):
            log.debug("date detected")
            try:
                dct[k] = datetime.strptime(v[:19], DATE_FORMAT)
            except:
                log.error("date parsing failed for '%s'", v[:19])
                pass
    return dct


class RestApiHome(ApiResource):
    permission_classes = (AllowAny,)

    def __init__(self, xmlrpc_port=33610, xmlrpc_use_ssl=True, api_key=None):
        Resource.__init__(self)
        url = '%(protocol)s://127.0.0.1:%(port)d/CloudMailing' % {'protocol': xmlrpc_use_ssl and 'https' or 'http', 'port': xmlrpc_port}
        self.proxy = Proxy(url, user='admin', password=api_key, allowNone=True,
                       useDateTime=True, connectTimeout=30.0)

    def render_GET(self, request):
        self.log_call(request)
        data = {
            'product_name': "CloudMailing",
            'product_version': __version__,
            'api_version': API_VERSION,
        }
        self.write_headers(request)
        return json.dumps(data)

    def _api_callback(self, data, request):
        request.setResponseCode(http_status.HTTP_200_OK)
        self.write_headers(request)
        # print data
        request.write(json.dumps({'status': 'ok', 'result': data}, default=json_default))
        request.finish()

    def render_POST(self, request):
        if not self.check_permissions([IsAdminUser()]):
            return self.access_forbidden(request)

        self.log_call(request)
        data = json.loads(request.content.read(), object_hook=datetime_parser)
        function = data['function']
        args = data.get('args', [])
        log.debug("Calling '%s(%s)'", function, repr(args))
        self.proxy.callRemote(str(function), *args)\
            .addCallback(self._api_callback, request)\
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET


class AuthenticateApi(ApiResource):
    """
    Resource to handle authentication requests
    """
    isLeaf = True
    serializer_class = serializers.UserSerializer
    permission_classes = (AllowAny,)

    def __init__(self):
        Resource.__init__(self)

    def render_GET(self, request):
        self.log_call(request)
        if self.check_permissions([IsAuthenticated()]):
            user = {
                'username': 'admin',
                'is_superuser': True,
                # 'groups': []
            }
            self.write_headers(request)
            return json.dumps(user, default=json_default)
        else:
            return self.access_forbidden(request)

    def render_POST(self, request):
        assert(isinstance(request, server.Request))
        content = request.content.read()
        self.log_call(request, content=content)
        data = json.loads(content)
        username = data.get('username')
        creds = credentials.UsernamePassword(username, data.get('password'))
        user = request.site.check_authentication(request, credentials=creds)

        if user:
            log_security.info("REST authentication success for user '%s' (%s)" % (username, request.getClientIP()))
            result = {
                'username': 'admin',
                'is_superuser': True,
                # 'groups': []
            }
            self.write_headers(request)
            return json.dumps(result, default=json_default)

        request.getSession().expire()
        request.setResponseCode(http_status.HTTP_401_UNAUTHORIZED)
        self.write_headers(request)
        log_security.warn("REST authentication failed for user '%s' (%s)" % (username, request.getClientIP()))
        return json.dumps({'error': "Authorization Failed!"})


class LogoutApi(ApiResource):
    """
    Resource to handle logout requests
    """
    isLeaf = True
    permission_classes = (AllowAny,)

    def render_POST(self, request):
        assert(isinstance(request, server.Request))
        self.log_call(request)
        username = self.get_user(request).username

        request.getSession().expire()
        request.setResponseCode(http_status.HTTP_200_OK)
        self.write_headers(request)
        log_security.info("User '%s' logged out (%s)" % (username, request.getClientIP()))
        return json.dumps({'status': "Logged out"})


class OsApi(ApiResource):
    isLeaf = True

    def __init__(self):
        Resource.__init__(self)

    def render_GET(self, request):
        # self.log_call(request)
        import psutil
        section = request.postpath and request.postpath.pop() or None
        if not section:
            data = {
                'platform': platform.platform(),
                'machine': platform.machine(),
                'name': platform.node(),
                'system': platform.system(),
                'version': platform.version(),
                'boot_time': psutil.boot_time()
            }
        elif section == 'cpu':
            cpu_times_percent = psutil.cpu_times_percent()
            data = {
                'total': cpu_times_percent.user + cpu_times_percent.system,
                'system': cpu_times_percent.system,
                'user': cpu_times_percent.user,
                'idle': cpu_times_percent.idle,
                # 'total_per_cpu': psutil.cpu_percent(percpu=True),
            }
        elif section == 'memory':
            vmem = psutil.virtual_memory()
            data = {
                'total': vmem.total,
                'available': vmem.available,
                'percent': vmem.percent,
                'used': vmem.used,
                'free': vmem.free,
            }
        elif section == 'disk':
            disk = psutil.disk_usage(settings.PROJECT_ROOT)
            data = {
                'total': disk.total,
                'used': disk.used,
                'free': disk.free,
                'percent': disk.percent,
            }
        else:
            data = {}
        self.write_headers(request)
        return json.dumps(data)


registerAdapter(CurrentUser, Session, ICurrentUser)


def make_rest_api(xmlrpc_port=33610, xmlrpc_use_ssl=True, api_key=None):

    api = RestApiHome(xmlrpc_port=xmlrpc_port, xmlrpc_use_ssl=True, api_key=api_key)
    api.putChild('authenticate', AuthenticateApi())
    api.putChild('logout', LogoutApi())
    api.putChild('mailings', ListMailingsApi())
    api.putChild('recipients', ListRecipientsApi())
    api.putChild('satellites', ListSatellitesApi())
    api.putChild('os', OsApi())
    return api