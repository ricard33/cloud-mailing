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
import email
import json
import platform
import re
from datetime import datetime
from xmlrpclib import Fault

from twisted.cred import credentials
from twisted.python.components import registerAdapter
from twisted.web import error as web_error, server
from twisted.web.resource import Resource
from twisted.web.server import Session
from twisted.web.xmlrpc import Proxy
from zope.interface import implements

from cloud_mailing.common.db_common import get_db
from ..common.api_common import ICurrentUser
from ..common.config_file import ConfigFile
from ..common.permissions import AllowAny, IsAdminUser, IsAuthenticated
from . import serializers
from .api_common import set_mailing_properties, pause_mailing, start_mailing, close_mailing, delete_mailing, \
    log_security
from .. import __version__
from ..common import http_status
from ..common import settings
from ..common.json_tools import json_default
from ..common.rest_api_common import ApiResource, log, ListModelMixin, RetrieveModelMixin, CurrentUser

__author__ = 'Cedric RICARD'

API_VERSION = 1
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
    # isLeaf = True
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
    # isLeaf = True
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


class ListMailingsApi(ListModelMixin, ApiResource):
    """
    Resource to handle requests on mailings
    """
    # isLeaf = True
    serializer_class = serializers.MailingSerializer

    def __init__(self):
        Resource.__init__(self)

    def getChild(self, name, request):
        if int_re.match(name):
            return MailingApi(int(name))
        return ApiResource.getChild(self, name, request)

    def render_GET(self, request):
        self.log_call(request)
        self.list(request)\
            .addCallback(lambda x: request.write(x)) \
            .addCallback(lambda x: request.finish()) \
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET


class MailingApi(RetrieveModelMixin, ApiResource):
    """
    Resource handling request on a specific mailing
    """
    serializer_class = serializers.MailingSerializer

    def __init__(self, mailing_id):
        Resource.__init__(self)
        self.mailing_id = mailing_id  # easier to read that object_id
        self.object_id = mailing_id

    def getChild(self, name, request):
        if name == 'recipients':
            return ListRecipientsApi(self.mailing_id)
        if name == 'content':
            return MailingContentApi(self.mailing_id)
        return ApiResource.getChild(self, name, request)

    def render_GET(self, request):
        self.log_call(request)
        self.retrieve(request)\
            .addCallback(lambda x: request.write(x)) \
            .addCallback(lambda x: request.finish()) \
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET

    def render_PATCH(self, request):
        return self.render_POST(request)

    def render_POST(self, request):
        content = request.content.read()
        self.log_call(request, content=content)
        data = json.loads(content)
        if 'status' in data:
            if len(data) > 1:
                request.setResponseCode(http_status.HTTP_400_BAD_REQUEST)
                self.write_headers(request)
                self.log.warning(" Mailing 'status' field should be changed alone.")
                return json.dumps({'error': " Mailing 'status' field should be changed alone."})

            status = data['status']
            if status == 'PAUSED':
                mailing = pause_mailing(self.mailing_id)
            elif status in ('READY', 'RUNNING'):
                mailing = start_mailing(self.mailing_id)
            elif status == 'FINISHED':
                mailing = close_mailing(self.mailing_id)
            else:
                request.setResponseCode(http_status.HTTP_400_BAD_REQUEST)
                self.write_headers(request)
                self.log.warning("Unsupported status value")
                return json.dumps({'error': "Unsupported status value"})

        else:  # 'status' not in data
            try:
                mailing = set_mailing_properties(self.mailing_id, data)
            except Fault, ex:
                request.setResponseCode(ex.faultCode)
                self.write_headers(request)
                self.log.error("Error setting mailing properties: %s", ex.faultString)
                return json.dumps({'error': ex.faultString})

        # finally returns the modified mailing
        self.write_headers(request)
        serializers.MailingSerializer().get(mailing.id)\
            .addCallback(lambda result: json.dumps(result, default=json_default)) \
            .addCallback(lambda data: request.write(data)) \
            .addCallback(lambda data: request.finish()) \
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET

    def render_DELETE(self, request):
        self.log_call(request)
        delete_mailing(self.mailing_id)
        self.write_headers(request)
        request.setResponseCode(http_status.HTTP_204_NO_CONTENT)
        return ""


class MailingContentApi(ApiResource):
    """
    Display mailing content
    """
    def __init__(self, mailing_id=None):
        Resource.__init__(self)
        self.mailing_id = mailing_id

    def render_GET(self, request):
        self.log_call(request)
        db = get_db()
        db.mailing.find_one({'_id': self.mailing_id})\
            .addCallback(self.cb_get_mailing, request)\
            .addErrback(self.eb_get_mailing, request)
        return server.NOT_DONE_YET

    def cb_get_mailing(self, mailing, request):
        mparser = email.parser.FeedParser()
        mparser.feed(mailing['header'])
        mparser.feed(mailing['body'])
        msg = mparser.close()


        def get_html_body(part):
            self.log.debug("***")
            import email.message
            assert (isinstance(part, email.message.Message))
            if part.is_multipart():
                self.log.debug(part.get_content_type())
                subtype = part.get_content_subtype()
                if subtype == 'mixed':
                    return get_html_body(part.get_payload(0))

                elif subtype == 'alternative':
                    for p in part.get_payload():
                        self.log.debug("  sub = %s", p.get_content_type())
                        if p.get_content_type() == 'text/html' or p.get_content_type() == "multipart/related":
                            return get_html_body(p)


                elif subtype == 'digest':
                    raise email.errors.MessageParseError, "multipart/digest not supported"

                elif subtype == 'parallel':
                    raise email.errors.MessageParseError, "multipart/parallel not supported"

                elif subtype == 'related':
                    return get_html_body(part.get_payload(0))

                else:
                    self.log.warn("Unknown multipart subtype '%s'" % subtype)

            else:
                maintype, subtype = part.get_content_type().split('/')
                if maintype == 'text':
                    self.log.debug("body found (%s/%s)", maintype, subtype)
                    # request.setHeader('Content-Type', part.get_content_type())
                    body = part.get_payload().encode('utf8')
                    self.log.debug("body: %s", type(body))
                    return body
                else:
                    self.log.warn("get_html_body(): can't handle '%s' parts" % part.get_content_type())
            return ""

        request.setResponseCode(http_status.HTTP_200_OK)
        body = get_html_body(msg)
        self.log.debug("**body: %s", type(body))

        request.write(get_html_body(msg))
        # request.write("<html><body><b>Email</b> content.</body></html>")
        request.finish()

    def eb_get_mailing(self, error, request):
        self.log.error("Error returning HTML content for mailing [%d]: %s", self.mailing_id, error)
        request.setResponseCode(http_status.HTTP_500_INTERNAL_SERVER_ERROR)
        request.write("<html><body><b>ERROR</b>: can't get content.</body></html>")
        request.finish()


class ListRecipientsApi(ListModelMixin, ApiResource):
    """
    Resource to handle requests on recipients
    """
    # isLeaf = True
    serializer_class = serializers.RecipientSerializer

    def __init__(self, mailing_id=None):
        Resource.__init__(self)
        self.mailing_id = mailing_id

    def getChild(self, name, request):
        if name:
            return RecipientApi(name)
        return ApiResource.getChild(self, name, request)

    def render_GET(self, request):
        self.log_call(request)
        kwargs = {}
        if self.mailing_id is not None:
            kwargs['mailing.$id'] = self.mailing_id
        self.list(request, **kwargs)\
            .addCallback(lambda x: request.write(x)) \
            .addCallback(lambda x: request.finish()) \
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET


class RecipientApi(RetrieveModelMixin, ApiResource):
    serializer_class = serializers.RecipientSerializer

    def __init__(self, recipient_id):
        Resource.__init__(self)
        self.recipient_id = recipient_id
        self.object_id = recipient_id

    def render_GET(self, request):
        self.log_call(request)
        self.retrieve(request) \
            .addCallback(lambda x: request.write(x)) \
            .addCallback(lambda x: request.finish()) \
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET


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
    api.putChild('os', OsApi())
    return api