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

import os

from twisted.cred import error

from ..common.encoding import force_bytes
from ..common import settings

__author__ = 'Cedric RICARD'


class AdminChecker(object):
    _credCache = None
    _cacheTimestamp = 0

    def _loadCredentials(self):
        from ..common.config_file import ConfigFile
        config = ConfigFile()
        config.read(settings.CONFIG_FILE)

        key = config.get('CM_MASTER', 'API_KEY', '')

        if not key:
            raise error.UnauthorizedLogin()
        return ((b'admin', key.encode()),)

    def check_credentials(self, credentials):
        username = force_bytes(credentials.username)
        if username == b'admin':
            if self._credCache is None or os.path.getmtime(settings.CONFIG_FILE) > self._cacheTimestamp:
                self._cacheTimestamp = os.path.getmtime(settings.CONFIG_FILE)
                self._credCache = dict(self._loadCredentials())
            if force_bytes(credentials.password) == self._credCache[username]:
                return username
        return None

