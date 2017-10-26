# Copyright 2015 Cedric RICARD
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

import email
import email.header

from .encoding import force_text

__author__ = 'Cedric RICARD'


def header_to_unicode(header_str):
    """
    Decodes an encoded header string and returns it into unicode string
    :param header_str: raw header string
    :return: An unicode string
    """
    l = []
    for txt, encoding in email.header.decode_header(header_str):
        if encoding is not None:
            l.append(txt.decode(encoding, errors='replace'))
        else:
            l.append(force_text(txt))
    return ''.join(l)
