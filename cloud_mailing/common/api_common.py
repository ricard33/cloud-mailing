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
from cStringIO import StringIO
import inspect
from twisted.web import xmlrpc, resource, http, static

__author__ = 'Cedric RICARD'

class HomePage(resource.Resource):
    sub_services = []

    def put_child(self, folder, rpc, add_introspection = False):
        if add_introspection:
            self.sub_services.append([folder, rpc])
            xmlrpc.addIntrospection(rpc)
        self.putChild(folder, rpc)

    def make_home_page(self):
        from .. import __version__ as VERSION
        s = StringIO()
        s.write("""<html lang="en"><head>
        <title>CloudMailing API</title>
        <link href="//netdna.bootstrapcdn.com/bootstrap/3.0.0/css/bootstrap.min.css" rel="stylesheet">
        <script src="//netdna.bootstrapcdn.com/bootstrap/3.0.0/js/bootstrap.min.js"></script>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>""")
        s.write(
            '<body><div class="container"><div class="page-header"><h1>CloudMailing API services <small>Version %s</small></h1></div>' % VERSION)
        if self.sub_services:
            for name, rpc in self.sub_services:
                s.write('''<div class="row">
                    <div class="col-md-2 col-md-offset-1"><h2><a href="%(name)s">%(name)s</a></h2></div>
                    <div class="col-md-8"><div class="well">%(description)s</div></div>
                </div>
                ''' % {'name': name, 'description': inspect.getdoc(rpc)})
        else:
            s.write('<style>.red { color: #FF0000; }</style>')
            s.write('<h2 class="red">Invalid License.</h2>')
        s.write("</div></body></html>")
        home = static.Data(s.getvalue(), "text/html")
        self.putChild("", home)


