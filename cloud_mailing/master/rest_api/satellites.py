from twisted.web import server
from twisted.web.resource import Resource

from cloud_mailing.master import serializers
from ...common.rest_api_common import ApiResource, ListModelMixin, integer_re, RetrieveModelMixin

__author__ = 'Cedric RICARD'


class ListSatellitesApi(ListModelMixin, ApiResource):
    serializer_class = serializers.SatelliteSerializer

    def __init__(self):
        Resource.__init__(self)

    def getChild(self, name, request):
        if integer_re.match(name):
            return SatelliteApi(int(name))
        return ApiResource.getChild(self, name, request)


class SatelliteApi(RetrieveModelMixin, ApiResource):
    isLeaf = True
    serializer_class = serializers.SatelliteSerializer

    def __init__(self, satellite_id):
        Resource.__init__(self)
        self.satellite_id = satellite_id  # easier to read that object_id
        self.object_id = satellite_id
