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
from xmlrpclib import Fault

from bson import json_util
from twisted.web import server, error as web_error

from twisted.web.resource import Resource
from twisted.web.xmlrpc import Proxy

from ..common.json_tools import json_default
from .api_common import set_mailing_properties, pause_mailing, start_mailing, close_mailing

from .models import relay_status, Mailing
from .serializers import MailingSerializer, RecipientSerializer
from ..common import http_status
from ..common.rest_api_common import ApiResource, log, regroup_args, ListModelMixin, RetrieveModelMixin
from .. import __version__
from ..common import settings

__author__ = 'Cedric RICARD'

DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
date_re = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
int_re = re.compile(r'^\d+$')


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
            'api_version': '0.1',
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
        self.log_call(request)
        data = json.loads(request.content.read(), object_hook=datetime_parser)
        function = data['function']
        args = data.get('args', [])
        log.debug("Calling '%s(%s)'", function, repr(args))
        self.proxy.callRemote(str(function), *args)\
            .addCallback(self._api_callback, request)\
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET


class ListMailingsApi(ListModelMixin, ApiResource):
    """
    Resource to handle requests on mailings
    """
    # isLeaf = True
    serializer_class = MailingSerializer

    def __init__(self):
        Resource.__init__(self)

    def getChild(self, name, request):
        if int_re.match(name):
            return MailingApi(int(name))
        return ApiResource.getChild(self, name, request)

    def render_GET(self, request):
        self.log_call(request)
        return self.list(request)


class MailingApi(RetrieveModelMixin, ApiResource):
    """
    Resource handling request on a specific mailing
    """
    serializer_class = MailingSerializer

    def __init__(self, mailing_id):
        Resource.__init__(self)
        self.mailing_id = mailing_id  # easier to read that object_id
        self.object_id = mailing_id

    def getChild(self, name, request):
        if name == 'recipients':
            return ListRecipientsApi(self.mailing_id)
        return ApiResource.getChild(self, name, request)

    def render_GET(self, request):
        self.log_call(request)
        return self.retrieve(request)

    def render_PATCH(self, request):
        self.log_call(request)
        content = request.content.read()
        data = json.loads(content)
        if 'status' in data:
            if len(data) > 1:
                request.setResponseCode(http_status.HTTP_400_BAD_REQUEST)
                self.write_headers(request)
                return json.dumps({'error': " Mailing 'status' field should be changed alone."})

            status = data['status']
            if status == 'PAUSED':
                mailing = pause_mailing(self.mailing_id)
            elif status == 'RUNNING':
                mailing = start_mailing(self.mailing_id)
            elif status == 'FINISHED':
                mailing = close_mailing(self.mailing_id)
            else:
                request.setResponseCode(http_status.HTTP_400_BAD_REQUEST)
                self.write_headers(request)
                return json.dumps({'error': "Unsupported status value"})

        else:  # 'status' not in data
            try:
                mailing = set_mailing_properties(self.mailing_id, data)
            except Fault, ex:
                request.setResponseCode(ex.faultCode)
                self.write_headers(request)
                return json.dumps({'error': self.faultString})

        # finally returns the modified mailing
        self.write_headers(request)
        result = MailingSerializer().get(mailing.id)
        return json.dumps(result, default=json_default)


class ListRecipientsApi(ListModelMixin, ApiResource):
    """
    Resource to handle requests on recipients
    """
    # isLeaf = True
    serializer_class = RecipientSerializer

    def __init__(self, mailing_id=None):
        Resource.__init__(self)
        self.mailing_id = mailing_id

    def getChild(self, name, request):
        if name:
            return RecipientApi(name)
        return ApiResource.getChild(self, name, request)

    def render_GET(self, request):
        self.log_call(request)
        return self.list(request)


class RecipientApi(RetrieveModelMixin, ApiResource):
    serializer_class = RecipientSerializer

    def __init__(self, recipient_id):
        Resource.__init__(self)
        self.recipient_id = recipient_id
        self.object_id = recipient_id

    def render_GET(self, request):
        self.log_call(request)
        return self.retrieve(request)


class SatelliteApi(ApiResource):
    def __init__(self):
        Resource.__init__(self)

    pass


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
                'user': cpu_times_percent.user,
                'system': cpu_times_percent.system,
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


def make_rest_api(xmlrpc_port=33610, xmlrpc_use_ssl=True, api_key=None):
    api = RestApiHome(xmlrpc_port=33610, xmlrpc_use_ssl=True, api_key=api_key)
    api.putChild('mailings', ListMailingsApi())
    api.putChild('recipients', ListRecipientsApi())
    api.putChild('os', OsApi())
    return api