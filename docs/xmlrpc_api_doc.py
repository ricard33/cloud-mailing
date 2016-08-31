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

__author__ = 'Cedric RICARD'

import sys

def format_xmlrpc_members_doc(app, what, name, obj, options, lines):
    print >>sys.stderr, "@@@@", name, lines
    # return (signature, return_annotation)

def setup(app):
    app.connect('autodoc-process-docstring', format_xmlrpc_members_doc)
    # pass
