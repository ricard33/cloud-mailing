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
from twisted.web import xmlrpc, resource, http, server, static
from twisted.internet import defer, protocol, reactor
from twisted.python import log
import os
import logging
import pydoc
import inspect
import re
import traceback
import xmlrpclib

Fault = xmlrpclib.Fault
Binary = xmlrpclib.Binary
Boolean = xmlrpclib.Boolean
DateTime = xmlrpclib.DateTime

try:
    withRequest = xmlrpc.withRequest
except AttributeError:
    def withRequest(f, *args, **kwargs):
        """
        Decorator to cause the request to be passed as the first argument
        to the method.
    
        If an I{xmlrpc_} method is wrapped with C{withRequest}, the
        request object is passed as the first argument to that method.
        For example::
    
            @withRequest
            def xmlrpc_echo(self, request, s):
                return s
        """
        f.withRequest = True
        return f

def doc_signature(*args, **kwargs):
    """
    Decorator to document signatures of a function.
    Should contains return type on last position.
    Can be used multiple time, for multiple signatures
    For example::

        @doc_signature('int', 'int', 'int')
        @doc_signature('float', 'float', 'float')
        def xmlrpc_add(self, a, b):
            return a + b
    """
    def _f(f):
        if not hasattr(f, 'signature'):
            f.signature = []
        f.signature.append(args)
        return f
    return _f


def doc_hide(f, *args, **kwargs):
    """
    Decorator to hide a method from documentation.
    """
    f.hide_from_documentation = True
    return f


log_cfg = logging.getLogger('config')
log_security = logging.getLogger('security')

class XmlRcpError(Exception):
    """Exception class allowing to return HTTP error code and associated message."""
    def __init__(self, http_code, error_msg):
        Exception.__init__(self, error_msg)
        self.http_code = http_code


class TwistedRPCServer(xmlrpc.XMLRPC):
    """ A class which works as an XML-RPC server with
    HTTP basic authentication """

    def __init__(self, user='', password=''):
        self._user = user
        self._password = password
        self._auth = (self._user !='')
        xmlrpc.XMLRPC.__init__(self)

    def xmlrpc_echo(self, x):
        return x

    def xmlrpc_ping(self):
        return 'OK'

    def render(self, request):
        """ Overridden 'render' method which takes care of
        HTTP basic authorization """

        if self._auth:
            cleartext_token = self._user + ':' + self._password
            user = request.getUser()
            passwd = request.getPassword()

            if user=='' and passwd=='':
                request.setResponseCode(http.UNAUTHORIZED)
                return 'Authorization required!'
            else:
                token = user + ':' + passwd
                if token != cleartext_token:
                    request.setResponseCode(http.UNAUTHORIZED)
                    return 'Authorization Failed!'

        request.content.seek(0, 0)
        args, functionPath = xmlrpclib.loads(request.content.read())
        try:
            function = self._getFunction(functionPath)
        except Fault, f:
            self._cbRender(f, request)
        else:
            request.setHeader("content-type", "text/xml")
            defer.maybeDeferred(function, *args).addErrback(
                self._ebRender
                ).addCallback(
                self._cbRender, request
                )

        return server.NOT_DONE_YET



def _authenticate(rpc_server, username, password, remote_ip):
    raise Fault(http.UNAUTHORIZED, 'Authorization Failed!')


class BasicHttpAuthXMLRPC(xmlrpc.XMLRPC):
    _anonymous_allowed = False
    _no_auth_for_local = False
    _user = None   # user object returned by authenticate method

    # Authenticate method.
    # Should take following parameters:
    #   - rpc_server : the xmlrpc server
    #   - username
    #   - password
    #   - remote_ip
    # and return a user object if successfully logged, or raise an xmlrpc.Fault exception else.
    _authenticate_method = _authenticate

    def render_POST(self, request):
        """ Overridden 'render_POST' method which takes care of
        HTTP basic authorization """
        
        if not self._anonymous_allowed and (request.getClientIP() != '127.0.0.1' or self._no_auth_for_local == False):
            user = request.getUser()
            passwd = request.getPassword()
            if user == '' and passwd == '':
                request.setResponseCode(http.UNAUTHORIZED)
                log_security.warn('XMLRPC connection refused for anonymous user (%s)' % request.getClientIP())
                f = Fault(http.UNAUTHORIZED, 'Authorization required!')
                self._cbRender(f, request)
                return server.NOT_DONE_YET
            remote_ip = request.getHeader('HTTP_X_FORWARDED_FOR')
            if remote_ip:
                remote_ip = remote_ip.split(':')[0].split(',')[0]
            else:
                remote_ip = request.getClientIP()
            try:
                # Warning: self is given as hidden argument, like a member function
                user = self._authenticate_method(username=request.getUser(), password=request.getPassword(), remote_ip=remote_ip)
                self._user = user
            except Fault, f:
                self._cbRender(f, request)
                return server.NOT_DONE_YET

        # Original Twisted code follows (only present in Twisted version >= 10.2)
        request.content.seek(0, 0)
        request.setHeader("content-type", "text/xml")
        try:
            if self.useDateTime:
                args, functionPath = xmlrpclib.loads(request.content.read(),
                    use_datetime=True)
            else:
                # Maintain backwards compatibility with Python < 2.5
                args, functionPath = xmlrpclib.loads(request.content.read())
        except Exception, e:
            f = Fault(self.FAILURE, "Can't deserialize input: %s" % (e,))
            self._cbRender(f, request)
        else:
            try:
                if hasattr(self, "lookupProcedure"):
                    function = self.lookupProcedure(functionPath)
                else:
                    function = self._getFunction(functionPath)
            except Fault, f:
                self._cbRender(f, request)
            else:
                # Use this list to track whether the response has failed or not.
                # This will be used later on to decide if the result of the
                # Deferred should be written out and Request.finish called.
                responseFailed = []
                request.notifyFinish().addErrback(responseFailed.append)
                if getattr(function, 'withRequest', False):
                    d = defer.maybeDeferred(function, request, *args)
                else:
                    d = defer.maybeDeferred(function, *args)
                d.addErrback(self._ebRender)
                d.addCallback(self._cbRender, request, responseFailed)
        return server.NOT_DONE_YET
            
    def _ebRender(self, failure):
        if isinstance(failure.value, Fault):
            return failure.value
        log.err(failure)
        if isinstance(failure.value, Exception):
            return Fault(self.FAILURE, failure.value.message)
        return Fault(self.FAILURE, "error")


class HTMLDoc(object):

    _repr_instance = pydoc.HTMLRepr()
    repr = _repr_instance.repr
    escape = _repr_instance.escape


    def heading(self, title):
        return '<div class="page-header"><h1>%s</div>' % title

    def section(self, title, contents, prelude=''):
        """Format a section with a heading."""
        result = '''<div class="panel panel-primary">
<div class="panel-heading">%(title)s</div>
<div class="panel-body">
''' % {'title': title}
        if prelude:
            result = result + '''
<div class"row">
    <div class="well col-md-offset-1">%(prelude)s</div>
</div>
''' % {'prelude': prelude}

        return result + '''
<div class="row">
    <div class="col-md-offset-1">%s</div>
</div></div></div>''' % contents

    def bigsection(self, title, *args):
        """Format a section with a big heading."""
        title = '<h2 class="panel-title">%s</h2>' % title
        return self.section(title, *args)

    def method_summary(self, method_names):
        l = '<ul>%s</ul>' % ''.join(['<li><a href="#method-%(name)s">%(name)s</a></li>' % {'name': name} for name in method_names])
        return self.section('Methods', l)

    def preformat(self, text):
        """Format literal preformatted text."""
        text = self.escape(text.expandtabs())
        return pydoc.replace(text, '\n\n', '\n \n', '\n\n', '\n \n',
                             ' ', '&nbsp;', '\n', '<br>\n')

    def breadcrumb(self, levels):
        result = StringIO()
        result.write('<ol class="breadcrumb">')
        for name, url in levels:
            if url:
                result.write('<li><a href="%(url)s">%(name)s</a></li>' % {'name': name, 'url': url})
            else:
                result.write('<li class="active">%(name)s</li>' % {'name': name, 'url': url})
        result.write('</ol>')
        return result.getvalue()

class ServerHTMLDoc(HTMLDoc):
    """Class used to generate HTML document for a server"""

    def page(self, title, contents):
        """Format an HTML page."""
        return '''
<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">
<html><head><title>CloudMailing: %s</title>
<link href="//netdna.bootstrapcdn.com/bootstrap/3.0.0/css/bootstrap.min.css" rel="stylesheet">
<script src="//netdna.bootstrapcdn.com/bootstrap/3.0.0/js/bootstrap.min.js"></script>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head><body bgcolor="#f0f0f8">
<div class="container">%s</div>
</body></html>''' % (title, contents)

    def grey(self, text): return '<span class="text-muted">%s</span>' % text

    def namelink(self, name, *dicts):
        """Make a link for an identifier, given name-to-URL mappings."""
        for dict in dicts:
            if name in dict:
                return '<a href="%s">%s</a>' % (dict[name], name)
        return name

    def formatvalue(self, object):
        """Format an argument default value as text."""
        return self.grey('=' + self.repr(object))

    def markup(self, text, escape=None, funcs={}, classes={}, methods={}):
        """Mark up some plain text, given a context of symbols to look for.
        Each context dictionary maps object names to anchor names."""
        escape = escape or self.escape
        results = []
        here = 0

        # XXX Note that this regular expression does not allow for the
        # hyperlinking of arbitrary strings being used as method
        # names. Only methods with names consisting of word characters
        # and '.'s are hyperlinked.
        pattern = re.compile(r'\b((http|ftp)://\S+[\w/]|'
                                r'RFC[- ]?(\d+)|'
                                r'PEP[- ]?(\d+)|'
                                r'(self\.)?((?:\w|\.)+))\b')
        while 1:
            match = pattern.search(text, here)
            if not match: break
            start, end = match.span()
            results.append(escape(text[here:start]))

            all, scheme, rfc, pep, selfdot, name = match.groups()
            if scheme:
                url = escape(all).replace('"', '&quot;')
                results.append('<a href="%s">%s</a>' % (url, url))
            elif rfc:
                url = 'http://www.rfc-editor.org/rfc/rfc%d.txt' % int(rfc)
                results.append('<a href="%s">%s</a>' % (url, escape(all)))
            elif pep:
                url = 'http://www.python.org/dev/peps/pep-%04d/' % int(pep)
                results.append('<a href="%s">%s</a>' % (url, escape(all)))
            elif text[end:end+1] == '(':
                results.append(self.namelink(name, methods, funcs, classes))
            elif selfdot:
                results.append('self.<strong>%s</strong>' % name)
            else:
                results.append(self.namelink(name, classes))
            here = end
        results.append(escape(text[here:]))
        return ''.join(results)

    def docroutine(self, object, name=None, mod=None,
                   funcs={}, classes={}, methods={}, cl=None):
        """Produce HTML documentation for a function or method object."""

        realname = getattr(object, "__name__", "")
        name = name or realname
        anchor = (cl and cl.__name__ or 'method') + '-' + name
        return_type = ''

        title = '<a name="%s"><strong>%s</strong></a>' % (
            self.escape(anchor), self.escape(name))

        if inspect.ismethod(object):
            args, varargs, varkw, defaults = inspect.getargspec(object.im_func)
            # exclude the argument bound to the instance, it will be
            # confusing to the non-Python user
            argspec = inspect.formatargspec (
                    args[1:],
                    varargs,
                    varkw,
                    defaults,
                    formatvalue=self.formatvalue
                )
            return_type = ''
        elif inspect.isfunction(object):
            args, varargs, varkw, defaults = inspect.getargspec(object)
            argspec = inspect.formatargspec(
                args, varargs, varkw, defaults, formatvalue=self.formatvalue)
            return_type = ''
        else:
            argspec = '(...)'
            return_type = ''

        if isinstance(object, tuple):
            argspec = object[0] or argspec
            docstring = object[1] or ""
        else:
            docstring = pydoc.getdoc(object)

        if isinstance(argspec, list):
            decl = []
            for args in argspec:
                return_type = args[-1]
                decl.append(title + "(" + ', '.join(args[0:-1]) + ")" + (return_type and self.grey(
                    ' : %s' % return_type)))
        else:
            decl = title + argspec + (return_type and self.grey(
                ' : %s' % return_type))

        doc = self.markup(
            docstring, self.preformat, funcs, classes, methods)
        doc = doc and '<dd><tt>%s</tt></dd>' % doc
        if isinstance(decl, list):
            return '<dl>%s%s</dl>\n' % (''.join(map(lambda d: '<dt>%s</dt>' % d, decl)),
                                       doc)
        else:
            return '<dl><dt>%s</dt>%s</dl>\n' % (decl, doc)

    def docserver(self, server_name, package_documentation, methods):
        """Produce HTML documentation for an XML-RPC server."""

        fdict = {}
        for key, value in methods.items():
            fdict[key] = '#-' + key
            #fdict[value] = fdict[key]

        server_name = self.escape(server_name)
        result = self.heading(server_name)
        result += self.breadcrumb([("Home", "/"), (server_name, None)])
        doc = self.markup(package_documentation, self.preformat, fdict)
        result += doc and '<div class="well">%s</div>' % doc
        result += self.method_summary(sorted(methods.keys()))
        contents = []
        method_items = sorted(methods.items())
        for key, value in method_items:
            contents.append(self.docroutine(value, key, funcs=fdict))
        result += self.bigsection(
            'Methods details', ' '.join(contents))

        return result

class XMLRPCDocGenerator(object):
    """Generates documentation for an Twisted XML-RPC server.

    This class is designed as mix-in and should not
    be constructed directly.
    """

    allowedMethods = ('POST', 'GET',)

    # setup variables used for HTML documentation
    server_name = 'XML-RPC Server Documentation'
    server_documentation = ''
    default_server_documentation = \
                                 "This server exports the following methods through the XML-RPC "\
                                 "protocol."
    server_title = 'XML-RPC Server Documentation'

    def set_server_title(self, server_title):
        """Set the HTML title of the generated server documentation"""

        self.server_title = server_title

    def set_server_name(self, server_name):
        """Set the name of the generated HTML server documentation"""

        self.server_name = server_name

    def set_server_documentation(self, server_documentation):
        """Set the documentation string for the entire server."""

        self.server_documentation = server_documentation

    def generate_html_documentation(self):
        """generate_html_documentation() => html documentation for the server

        Generates HTML documentation for the server using introspection for
        installed functions and instances that do not implement the
        _dispatch method. Alternatively, instances can choose to implement
        the _get_method_argstring(method_name) method to provide the
        argument string used in the documentation and the
        _methodHelp(method_name) method to provide the help text used
        in the documentation."""

        methods = {}

        #pylint: disable-msg=E1101
        if hasattr(self, "listProcedures"):
            listProcedures = self.listProcedures
            lookupProcedure = self.lookupProcedure
        else:
            listProcedures = self._listFunctions
            lookupProcedure = self._getFunction

        for method_name in listProcedures():
            method = lookupProcedure(method_name)
            #pylint: enable-msg=E1101

            if getattr(method, 'hide_from_documentation', False):
                continue
            method_info = [None, None] # argspec, documentation
            #method_info[0] = '(%s)' % ', '.join(getattr(method, 'signature', [[]])[0])
            method_info[0] = getattr(method, 'signature', None) or []
            method_info[1] = (getattr(method, 'help', None)
                              or getattr(method, '__doc__', None) or '')

            method_info = tuple(method_info)
            methods[method_name] = method_info

        documenter = ServerHTMLDoc()
        documentation = documenter.docserver(
                                self.server_name,
                                getattr(self.__class__, '__doc__', None) or self.server_documentation or self.default_server_documentation,
                                methods
                            )

        return documenter.page(self.server_title, documentation)

    def render_GET(self, request):
        request.content.seek(0, 0)
        
        content = self.generate_html_documentation()
        
        request.setHeader("content-type", "text/html")
        request.setHeader("content-length", str(len(content)))
        request.write(content)
        request.finish()

        return server.NOT_DONE_YET

    
#--------------------------------------------



