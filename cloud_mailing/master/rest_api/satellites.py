# Copyright 2015-2019 Cedric RICARD
#
# This file is part of CloudMailing.
#
# CloudMailing is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CloudMailing is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with CloudMailing.  If not, see <http://www.gnu.org/licenses/>.

from twisted.web import server
from twisted.web.resource import Resource

from .. import serializers
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
