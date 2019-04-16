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

import pickle as pickle
import logging
import re
import time
from datetime import datetime

import pymongo
import txmongo.filter
from bson import DBRef
from twisted.internet import defer
from twisted.spread import util

from ..common.db_common import get_db
from ..common.singletonmixin import Singleton
from . import settings_vars
from .models import MAILING_STATUS, RECIPIENT_STATUS

__author__ = 'Cedric RICARD'


class MonitorSatellitesTask(Singleton):
    def __init__(self):
        self.log = logging.getLogger("monitor")

    def _get_avatar(self, serial):
        from .cloud_master import mailing_portal

        if mailing_portal:
            mailing_master = mailing_portal.realm
            return mailing_master.avatars.get(serial)
        else:
            self.log.error("Can't get MailingPortal object!")


    @defer.inlineCallbacks
    def run(self):
        try:
            db = get_db()

            all_satellites = yield db.cloudclient.find({'enabled': True, 'paired': True})

            for satellite in all_satellites:
                avatar = self._get_avatar(satellite['serial'])
                if not avatar:
                    self.log.error("Can't get avatar for '%s'. Client seems to be disconnected.", satellite['serial'])
                    continue
                yield avatar.set_settings(satellite.get('settings', {}))

        except:
            self.log.exception("Exception in MonitorSatellitesTask.run() function.")
