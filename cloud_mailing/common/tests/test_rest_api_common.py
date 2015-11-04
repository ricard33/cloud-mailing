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
from datetime import datetime

from cloud_mailing.common.rest_api_common import regroup_args
from cloud_mailing.master.models import MAILING_STATUS
from cloud_mailing.master.tests import factories
import json
from twisted.web.http_headers import Headers
from twisted.internet import reactor
from twisted.trial.unittest import TestCase

from cloud_mailing.common import http_status
from ...common.unittest_mixins import CommonTestMixin, DatabaseMixin, RestApiTestMixin

__author__ = 'Cedric RICARD'

class RegroupArgsTestCase(TestCase):

    def test_regroup_args(self):
        self.assertDictEqual({'.filter': 'total'}, regroup_args({'.filter': ['total']}))
        self.assertDictEqual({'.limit': 100}, regroup_args({'.limit': ['100']}))
        self.assertDictEqual({'status': ['FILLING_RECIPIENTS', 'READY', 'RUNNING', 'PAUSED']},
                             regroup_args({'status': ['FILLING_RECIPIENTS', 'READY', 'RUNNING', 'PAUSED']}))
