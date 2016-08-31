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

from twisted.trial.unittest import TestCase
from ..email_tools import header_to_unicode

__author__ = 'Cedric RICARD'


class RegroupArgsTestCase(TestCase):

    def test_header_to_unicode(self):
        # Example from RFC2047 page 12
        self.assertEqual(u"a", header_to_unicode("=?ISO-8859-1?Q?a?="))
        self.assertEqual(u"ab", header_to_unicode("=?ISO-8859-1?Q?a?= =?ISO-8859-1?Q?b?="))
        self.assertEqual(u"ab", header_to_unicode("=?ISO-8859-1?Q?a?= =?UTF-8?Q?b?="))
        self.assertEqual(u"a b", header_to_unicode("=?ISO-8859-1?Q?a?= b"))
        self.assertEqual(u'C\xe9dric RICARD <my-mailing@unittest.cloud-mailing.net>',
                         header_to_unicode("=?UTF-8?B?Q8OpZHJpYyBSSUNBUkQ=?= <my-mailing@unittest.cloud-mailing.net>"))
