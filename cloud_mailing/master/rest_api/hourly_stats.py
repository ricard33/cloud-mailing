from twisted.web import server
from twisted.web.resource import Resource

from cloud_mailing.master import serializers
from ...common.rest_api_common import ApiResource, ListModelMixin, integer_re, RetrieveModelMixin

__author__ = 'Cedric RICARD'


class HourlyStatsApi(ListModelMixin, ApiResource):
    isLeaf = True
    serializer_class = serializers.HourlyStatsSerializer

