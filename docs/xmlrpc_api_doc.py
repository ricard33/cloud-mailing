__author__ = 'Cedric RICARD'

import sys

def format_xmlrpc_members_doc(app, what, name, obj, options, lines):
    print >>sys.stderr, "@@@@", name, lines
    # return (signature, return_annotation)

def setup(app):
    app.connect('autodoc-process-docstring', format_xmlrpc_members_doc)
    # pass
