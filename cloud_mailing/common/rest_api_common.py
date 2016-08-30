import json
import logging
import re
from datetime import datetime
from xmlrpclib import Fault

import pymongo
from twisted.internet import defer
from twisted.web.resource import Resource
from twisted.web import error as web_error, server
from zope.interface import implements

from .api_common import ICurrentUser, AuthenticatedSite
from .permissions import IsAuthenticated, BasePermission
from .json_tools import json_default
from . import http_status
from . import settings

log = logging.getLogger('api')


class NotFound(Exception):
    pass


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, datetime):
        serial = obj.isoformat()
        return serial


integer_re = re.compile(r"^\d+$")


def simplify_value(v):
    if isinstance(v,list) and len(v) == 1:
        return simplify_value(v[0])
    elif isinstance(v, basestring) and integer_re.match(v):
        return int(v)
    return v


def regroup_args(dd):
    ret = {}
    for k,v in dd.items():
        ret[k] = simplify_value(v)
    return ret


def make_sort_filter(sort_string):
    if sort_string:
        orientation = sort_string[0] == '-' and pymongo.DESCENDING or pymongo.ASCENDING
        return [(sort_string.strip('-'), orientation)]
    return None


class ApiResource(Resource):
    serializer_class = None
    request = None
    object_id = None
    log = log
    permission_classes = (IsAuthenticated,)

    def get_serializer(self, *args, **kwargs):
        """
        Return the serializer instance that should be used for validating and
        deserializing input, and for serializing output.
        """
        serializer_class = self.get_serializer_class()
        kwargs['context'] = self.get_serializer_context()
        return serializer_class(*args, **kwargs)

    def get_serializer_class(self):
        """
        Return the class to use for the serializer.
        Defaults to using `self.serializer_class`.
        You may want to override this if you need to provide different
        serializations depending on the incoming request.
        (Eg. admins get full serialization, others get basic serialization)
        """
        assert self.serializer_class is not None, (
            "'%s' should either include a `serializer_class` attribute, "
            "or override the `get_serializer_class()` method."
            % self.__class__.__name__
        )

        return self.serializer_class

    def get_serializer_context(self):
        """
        Extra context provided to the serializer class.
        """
        assert(self.request is not None)
        return {
            'request': self.request,
            'view': self
        }

    def get_object_id(self):
        """
        Returns the object the view is displaying

        Defaults to using `self.object_id`.
        You may want to override this if you need to provide different
        id depending on the incoming request.
        """
        assert self.object_id is not None, (
            "'%s' should either include a `object_id` attribute, "
            "or override the `get_object_id()` method."
            % self.__class__.__name__
        )

        return self.object_id

    def getChild(self, name, request):
        """Allows this resource to be selected with a trailing '/'."""
        if name == '':
            return self
        return Resource.getChild(self, name, request)

    def write_headers(self, request):
        request.setHeader('Content-Type', 'application/json')
        request.setHeader('Access-Control-Allow-Origin', '*')
        request.setHeader('Access-Control-Allow-Credentials', 'true')
        request.setHeader('Access-Control-Allow-Headers', 'accept, content-type')
        request.setHeader('Access-Control-Allow-Methods', 'DELETE,GET,HEAD,PATCH,POST,PUT')

    def _on_error(self, err, request):
        self.write_headers(request)
        if err.check(Fault):
            log.error("[%s] %s", str(self.__class__), err.value.faultString)
            request.setResponseCode(err.value.faultCode)
            request.write(json.dumps({'error': repr(err.value.faultString)}))
        else:
            log.error("[%s] %s", str(self.__class__), err.value)
            request.setResponseCode(http_status.HTTP_500_INTERNAL_SERVER_ERROR)
            request.write(json.dumps({'error': repr(err.value)}))
        request.finish()

    def log_call(self, request, content=None):
        if content:
            log.debug('%s: %s (%s, %s)', request.method.upper(), request.path, request.args, content)
        else:
            log.debug('%s: %s (%s)', request.method.upper(), request.path, request.args)

    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        """
        return [permission() for permission in self.permission_classes]

    def check_permissions(self, permissions=None):
        if permissions is None:
            permissions = self.get_permissions()
        for perm in permissions:
            assert(isinstance(perm, BasePermission))
            if not perm.has_permission(self.request, self):
                return False
        return True

    def render(self, request):
        assert(isinstance(request, server.Request))
        assert(isinstance(request.site, AuthenticatedSite))
        self.request = request
        request.user = request.site.check_authentication(request)

        request.user = None
        if not self.check_permissions():
            return self.access_forbidden(request)

        return Resource.render(self, request)

    def access_forbidden(self, request):
        request.setResponseCode(http_status.HTTP_403_FORBIDDEN)
        self.write_headers(request)
        self.log.warn(
            "Access forbidden for resource '%s' (user=%s; ip=%s)" % (request.path, request.user, request.getClientIP()))
        return json.dumps({'error': "Forbidden"})

    def render_OPTIONS(self, request):
        self.log_call(request)
        self.write_headers(request)
        # request.setHeader('Access-Control-Allow-Origin', '*')
        return ''

    def get_user(self, request):
        """
        Returns the current logged user (from session).
        :param request: the twisted.web.server.Request object
        :return: a ICurrentUser instance
        """
        assert(isinstance(request, server.Request))
        session = request.getSession()
        return ICurrentUser(session)


class CurrentUser(object):
    implements(ICurrentUser)

    def __init__(self, session):
        self.username = ''
        self.is_authenticated = False
        self.is_superuser = False

    def __str__(self):
        return b"%s(username=%s, is_auth=%s, is_super=%s)" % (self.__class__, self.username, self.is_authenticated, self.is_superuser)

# View Mixins


class ListModelMixin(object):
    """
    List a queryset.
    """

    def render_GET(self, request):
        self.log_call(request)
        self.list(request)\
            .addCallback(lambda x: request.write(x)) \
            .addCallback(lambda x: request.finish()) \
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET

    @defer.inlineCallbacks
    def list(self, request, *args, **kwargs):
        _args = regroup_args(request.args)
        _args.update(kwargs)
        fields_filter = _args.pop('.filter', 'default')
        serializer = self.get_serializer_class()(fields_filter=fields_filter)
        self.write_headers(request)
        limit = _args.pop('.limit', settings.PAGE_SIZE)
        offset = _args.pop('.offset', 0)
        sort = make_sort_filter(_args.pop('.sort', None))
        try:
            result = yield serializer.find(_args, skip = offset, limit = limit, sort=sort)
            defer.returnValue(json.dumps(result, default=json_default))
        except ValueError, ex:
            raise web_error.Error(http_status.HTTP_406_NOT_ACCEPTABLE, ex.message)


class RetrieveModelMixin(object):
    """
    Retrieve a model instance.
    """
    def render_GET(self, request):
        self.log_call(request)
        self.retrieve(request)\
            .addCallback(lambda x: request.write(x)) \
            .addCallback(lambda x: request.finish()) \
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET

    @defer.inlineCallbacks
    def retrieve(self, request, *args, **kwargs):
        try:
            _filter = request.args.get('.filter', 'default')
            serializer = self.get_serializer_class()(fields_filter=_filter)
            self.write_headers(request)
            result = yield serializer.get(self.get_object_id())
            defer.returnValue(json.dumps(result, default=json_default))
        except NotFound:
            raise web_error.Error(http_status.HTTP_404_NOT_FOUND)
