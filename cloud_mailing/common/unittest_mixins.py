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

import json
import os

from mogo import connect
from mogo.connection import Connection
from twisted.internet.defer import succeed
from twisted.web.iweb import IBodyProducer
from zope.interface import implementer

from .config_file import ConfigFile
from .models import Settings
from . import settings
from .db_common import Db

__author__ = 'ricard'


class CommonTestMixin(object):
    def setup_settings(self):
        Settings.set('TEST_MODE', True)
        config = ConfigFile()
        config.read(settings.CONFIG_FILE)

        self.api_key = 'the_API_key'
        config.set('CM_MASTER', 'API_KEY', self.api_key)
        if not os.path.exists(settings.CONFIG_PATH):
            os.makedirs(settings.CONFIG_PATH)
        with open(settings.CONFIG_FILE, 'wt') as fp:
            config.write(fp)

    def clear_settings(self):
        if os.path.exists(settings.CONFIG_FILE):
            os.remove(settings.CONFIG_FILE)


class DatabaseMixin(object):
    def connect_to_db(self, db_name=None):
        if db_name is None:
            db_name = settings.TEST_DATABASE
        self.db_conn = connect(db_name)
        self.db_sync = self.db_conn[db_name]
        if Db.isInstantiated():
            self.db = Db.getInstance().db
        else:
            self.db = Db.getInstance(db_name, pool_size=1).db

        # self.db_conn.drop_database(db_name)
        db = Connection.instance().get_database()
        for col in db.collection_names(include_system_collections=False):
            if not col.startswith('_'):
                db.drop_collection(col)

    def disconnect_from_db(self):
        self.db_conn.close()
        return Db.disconnect()\
            .addBoth(lambda x: Db._forgetClassInstanceReferenceForTesting())


@implementer(IBodyProducer)
class JsonProducer(object):

    def __init__(self, body):
        self.body = json.dumps(body).encode()
        self.length = len(self.body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass


