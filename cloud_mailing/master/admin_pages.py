# Copyright 2015-2019 Cedric RICARD
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
