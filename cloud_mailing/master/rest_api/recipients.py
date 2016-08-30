from twisted.web import server
from twisted.web.resource import Resource

from ...common.rest_api_common import ListModelMixin, ApiResource, RetrieveModelMixin
from .. import serializers

__author__ = 'Cedric RICARD'


# noinspection PyPep8Naming
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


# noinspection PyPep8Naming
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
