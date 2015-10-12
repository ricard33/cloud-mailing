import json
import logging
from datetime import datetime
from xmlrpclib import Fault
from twisted.web.resource import Resource
from cloud_mailing.common import http_status

log = logging.getLogger('api')


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, datetime):
        serial = obj.isoformat()
        return serial


class ApiResource(Resource):
    def getChild(self, name, request):
        """Allows this resource to be selected with a trailing '/'."""
        if name == '':
            return self
        return Resource.getChild(self, name, request)

    def write_headers(self, request):
        request.setHeader('Content-Type', 'application/json')

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

    def log_call(self, request):
        log.debug('%s: %s (%s)', request.method.upper(), request.path, request.args)
