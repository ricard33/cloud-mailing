import json
from xmlrpclib import Fault

import re
from twisted.web import server
from twisted.web.resource import Resource

from ...common import http_status
from ...common.json_tools import json_default
from ...common.rest_api_common import ListModelMixin, ApiResource, RetrieveModelMixin, integer_re
from .. import serializers
from ..api_common import pause_mailing, start_mailing, close_mailing, set_mailing_properties, delete_mailing
from .recipients import ListRecipientsApi
from .mailing_contents import MailingContentApi

__author__ = 'Cedric RICARD'


# noinspection PyPep8Naming
class ListMailingsApi(ListModelMixin, ApiResource):
    """
    Resource to handle requests on mailings
    """
    # isLeaf = True
    serializer_class = serializers.MailingSerializer

    def __init__(self):
        Resource.__init__(self)

    def getChild(self, name, request):
        if integer_re.match(name):
            return MailingApi(int(name))
        return ApiResource.getChild(self, name, request)

    def render_GET(self, request):
        self.log_call(request)
        self.list(request)\
            .addCallback(lambda x: request.write(x)) \
            .addCallback(lambda x: request.finish()) \
            .addErrback(self._on_error, request)
        return server.NOT_DONE_YET


# noinspection PyPep8Naming
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
