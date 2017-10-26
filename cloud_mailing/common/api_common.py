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

import inspect
import logging
from io import StringIO

from twisted.cred import error
from twisted.web import xmlrpc, resource, static
from twisted.web.server import Site
from zope.interface import Interface, Attribute

__author__ = 'Cedric RICARD'


class HomePage(resource.Resource):
    sub_services = []

    def put_child(self, folder, rpc, add_introspection=False):
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


class ICurrentUser(Interface):
    """
    Currently logged user. Object stored in session.
    """
    username = Attribute("Logged username")
    is_authenticated = Attribute("Is current user authenticated?")
    is_superuser = Attribute("Is current user a superuser with powerfull rights?")


class AuthenticatedSite(Site):
    credentialsCheckers = []
    credentialFactories = []

    def _selectParseHeader(self, header):
        """
        Choose an C{ICredentialFactory} from C{credentialFactories}
        suitable to use to decode the given I{Authenticate} header.

        @type header: L{bytes}

        @return: A two-tuple of a factory and the remaining portion of the
            header value to be decoded or a two-tuple of C{None} if no
            factory can decode the header value.
        """
        elements = header.split(b' ')
        scheme = elements[0].lower()
        for fact in self.credentialFactories:
            if fact.scheme == scheme:
                return (fact, b' '.join(elements[1:]))
        return (None, None)

    def check_authentication(self, request, credentials=None):
        session = request.getSession()
        user = ICurrentUser(session)
        if user.is_authenticated:
            return user

        if credentials is None:
            authheader = request.getHeader('authorization')
            if not authheader:
                return None

            factory, respString = self._selectParseHeader(authheader.encode())
            if factory is None:
                return None
            try:
                credentials = factory.decode(respString, request)
            except error.LoginFailed:
                return None
            except:
                logging.error("Unexpected failure from credentials factory")
                return None

        for checker in self.credentialsCheckers:
            user.username = checker.check_credentials(credentials)
            if user.username:
                user.is_authenticated = True
                user.is_superuser = user.username == b'admin'
                return user

        return None
