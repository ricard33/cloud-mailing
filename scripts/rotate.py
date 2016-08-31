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

from cStringIO import StringIO

import sys

__author__ = 'Cedric RICARD'


def rotate(value, rank):
    """

    :param value:
    :param rank:
    :return: the rotated string

    >>> rotate("abc", 3)
    'def'
    >>> rotate("https://docs.python.org/2/library/doctest.html", 13)
    'uggcf://qbpf.clguba.bet/2/yvoenel/qbpgrfg.ugzy'
    """
    output = StringIO()
    for c in value:
        if 'A' <= c <= 'Z':
            c2 = ord(c) + rank
            if c2 > ord('Z'):
                c2 -= 26
            output.write(chr(c2))
        elif 'a' <= c <= 'z':
            c2 = ord(c) + rank
            if c2 > ord('z'):
                c2 -= 26
            output.write(chr(c2))
        else:
            output.write(c)

    return output.getvalue()


def print_all_roration(value):
    for i in range(25):
        print "%d --> %s" % (i+1, rotate(value, i+1))


if __name__ == '__main__':
    print_all_roration(sys.argv[1])
