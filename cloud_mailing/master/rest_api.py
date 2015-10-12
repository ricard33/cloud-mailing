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
from twisted.web import server
from twisted.web.resource import Resource
from ..common import http_status
from ..common.rest_api_common import ApiResource, log, json_serial
from .. import __version__
from ..common import settings

__author__ = 'Cedric RICARD'

DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
date_re = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
int_re = re.compile(r'^\d$')


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

    def __init__(self):
        Resource.__init__(self)

    def render_GET(self, request):
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
        request.write(json.dumps({'status': 'ok', 'result': data}, default=json_serial))
        request.finish()

    def render_POST(self, request):
        data = json.loads(request.content.read(), object_hook=datetime_parser)
        function = data['function']
        args = data.get('args', [])
        log.debug("Calling '%s(%s)'", function, repr(args))
        self.proxy.callRemote(str(function), *args)\
            .addCallback(self._api_callback, request)\
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET


class ListMailingsApi(ApiResource):
    """
    Resource to handle requests on mailings
    """
    # isLeaf = True
    def __init__(self):
        Resource.__init__(self)

    def getChild(self, name, request):
        """Allows this resource to be selected with a trailing '/'."""
        if int_re.match(name):
            return MailingApi(int(name))
        return ApiResource.getChild(self, name, request)

    def _list_received(self, data, request):
        request.setResponseCode(http_status.HTTP_200_OK)
        self.write_headers(request)
        results = {
            'count': len(data),
            'results': data
        }
        request.write(json.dumps(results, default=json_serial))
        request.finish()

    def render_GET(self, request):
        args = []
        if 'status' in request.args:
            args.append({'status': request.args['status']})
        self.proxy.callRemote("list_mailings", *args)\
            .addCallback(self._list_received, request)\
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET


class MailingApi(ApiResource):
    """
    Resource handling request on a specific mailing
    """
    def __init__(self, mailing_id):
        Resource.__init__(self)
        self.mailing_id = mailing_id

    def _list_received(self, data, request):
        request.setResponseCode(http_status.HTTP_200_OK)
        self.write_headers(request)
        request.write(json.dumps(data[0], default=json_serial))
        request.finish()

    def _status_received(self, data, request):
        request.setResponseCode(http_status.HTTP_200_OK)
        self.write_headers(request)
        request.write(json.dumps({'id': self.mailing_id, 'status': data}, default=json_serial))
        request.finish()

    def render_GET(self, request):
        self.proxy.callRemote("list_mailings", {'id': [self.mailing_id]})\
            .addCallback(self._list_received, request)\
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET

    def render_PATCH(self, request):
        data = json.loads(request.content.read())
        if 'status' in data:
            status = data['status']
            if status == 'PAUSED':
                self.proxy.callRemote("pause_mailing", self.mailing_id)\
                    .addCallback(self._status_received, request)\
                    .addErrback(self._on_error, request)
                return server.NOT_DONE_YET
            elif status == 'RUNNING':
                self.proxy.callRemote("start_mailing", self.mailing_id)\
                    .addCallback(self._status_received, request)\
                    .addErrback(self._on_error, request)
                return server.NOT_DONE_YET
            request.setResponseCode(http_status.HTTP_400_BAD_REQUEST)
            self.write_headers(request)
            return json.dumps({'error': "Unsupported status value"})
        else:
            request.setResponseCode(http_status.HTTP_400_BAD_REQUEST)
            self.write_headers(request)
            return json.dumps({'error': "Only 'status' changes are currently supported."})


class RecipientsApi(ApiResource):
    def __init__(self):
        Resource.__init__(self)

    pass


class SatelliteApi(ApiResource):
    def __init__(self):
        Resource.__init__(self)

    pass


class OsApi(ApiResource):
    isLeaf = True

    def __init__(self):
        Resource.__init__(self)

    def render_GET(self, request):
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


def make_rest_api():
    api = RestApiHome()
    api.putChild('mailings', ListMailingsApi())
    api.putChild('recipients', RecipientsApi())
    api.putChild('os', OsApi())
    return api