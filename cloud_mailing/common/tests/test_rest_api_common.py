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

import pymongo
from twisted.trial.unittest import TestCase

from ..rest_api_common import decode_and_regroup_args, make_sort_filter

__author__ = 'Cedric RICARD'


class RegroupArgsTestCase(TestCase):
    def test_regroup_args(self):
        self.assertDictEqual({'.filter': 'total'}, decode_and_regroup_args({'.filter': ['total']}))
        self.assertDictEqual({'.filter': 'total'}, decode_and_regroup_args({b'.filter': [b'total']}))
        self.assertDictEqual({'.limit': 100}, decode_and_regroup_args({'.limit': ['100']}))
        self.assertDictEqual({'status': ['FILLING_RECIPIENTS', 'READY', 'RUNNING', 'PAUSED']},
                             decode_and_regroup_args({'status': ['FILLING_RECIPIENTS', 'READY', 'RUNNING', 'PAUSED']}))

    def test_make_sort_filter(self):
        self.assertEqual([('field', pymongo.ASCENDING)], make_sort_filter('field'))
        self.assertEqual([('field', pymongo.DESCENDING)], make_sort_filter('-field'))
