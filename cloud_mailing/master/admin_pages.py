import logging
import os
import sys

from twisted.web.static import File

from ..common import settings

WEB_SRC_ROOT = os.path.join(settings.PROJECT_ROOT, 'web')
TMP_FOLDER = os.path.join(WEB_SRC_ROOT, '.tmp')


def make_admin_pages():
    if '--dev' in sys.argv:
        logging.warning("Running in development mode. All LS, CSS and HTML files are read from sources.")
        root = File(os.path.join(WEB_SRC_ROOT, 'app'))
        root.putChild(b'', File(os.path.join(TMP_FOLDER, 'index.html')))
        for url, folder in ((b'node_modules', 'node_modules'),
                            (b'.tmp', '.tmp'),
                            (b'js', 'js'),
                            (b'img', 'img'),
                            (b'fonts', '../static/fonts'),
                            (b'template', 'html/template'),
                            ):
            root.putChild(url, File(os.path.join(WEB_SRC_ROOT, folder)))
    else:
        root = File(settings.STATIC_ROOT)
    return root
