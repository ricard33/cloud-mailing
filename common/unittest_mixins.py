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

from mogo import connect
from mogo.connection import Connection
from common import settings

__author__ = 'ricard'


class DatabaseMixin(object):
    def connect_to_db(self):
        self.db_conn = connect(settings.TEST_DATABASE)
        # self.db_conn.drop_database(settings.TEST_DATABASE)
        db = Connection.instance().get_database()
        for col in db.collection_names(include_system_collections=False):
            db.drop_collection(col)

    def disconnect_from_db(self):
        self.db_conn.disconnect()
