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

import email
import email.header

__author__ = 'Cedric RICARD'


def header_to_unicode(header_str):
    """
    Decodes an encoded header string and returns it into unicode string
    :param header_str: raw header string
    :return: An unicode string
    """
    l = []
    last_encoding = None
    for txt, encoding in email.header.decode_header(header_str):
        if encoding is not None:
            l.append(txt.decode(encoding, errors='replace'))
            last_encoding = encoding
        else:
            if last_encoding:  # in the case of encoded-word followed by unencoded text, spaces must be preserved
                l.append(' ')
            last_encoding = None
            l.append(txt)
    return ''.join(l)
