import json
import logging
import re
from datetime import datetime
from xmlrpclib import Fault

import pymongo
from twisted.web.resource import Resource
from twisted.web import error as web_error

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


integer_re = re.compile(r"\d+")


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

    def render_OPTIONS(self, request):
        self.log_call(request)
        self.write_headers(request)
        # request.setHeader('Access-Control-Allow-Origin', '*')
        return ''


# View Mixins


class ListModelMixin(object):
    """
    List a queryset.
    """
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
            result = serializer.find(_args, skip = offset, limit = limit, sort=sort)
            return json.dumps(result, default=json_default)
        except ValueError, ex:
            raise web_error.Error(http_status.HTTP_406_NOT_ACCEPTABLE, ex.message)


class RetrieveModelMixin(object):
    """
    Retrieve a model instance.
    """
    def retrieve(self, request, *args, **kwargs):
        try:
            _filter = request.args.get('.filter', 'default')
            serializer = self.get_serializer_class()(fields_filter=_filter)
            self.write_headers(request)
            result = serializer.get(self.get_object_id())
            return json.dumps(result, default=json_default)
        except NotFound:
            raise web_error.Error(http_status.HTTP_404_NOT_FOUND)
