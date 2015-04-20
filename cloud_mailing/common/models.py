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

from datetime import datetime
import logging
from mogo import Model, Field

def safe_int(value):
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0

class Sequence(Model):

    @staticmethod
    def get_next(name):
        return Sequence._get_collection().find_and_modify({'_id': name}, {'$inc': {'seq': 1}}, new=True, upsert=True)['seq']


class Settings(Model):
    # id              = models.AutoField(primary_key=True)
    var_name        = Field(required=True)
    var_value       = Field()
    date_created    = Field(datetime, default=datetime.utcnow)
    last_modified   = Field(datetime, default=datetime.utcnow)

    @staticmethod
    def set(name, value):
        var = Settings.search(var_name=name).first()
        if var:
            old_value = var.var_value
            var.var_value = value
            var.last_modified = datetime.utcnow()
            var.save()
            return old_value
        else:
            Settings.create(var_name=name, var_value=value)

    @classmethod
    def get_str(cls, name, default=None):
        var = Settings.search(var_name=name).first()
        if var:
            return var.var_value
        return default

    @staticmethod
    def get_bool(name, default = None):
        value = Settings.get_str(name, default)
        if isinstance(value, basestring):
            if value.lower() == 'true' or safe_int(value) != 0:
                return True
            return False
        return value and int(value) != 0
    
    @staticmethod
    def get_int(name, default = None):
        var = Settings.search(var_name=name).first()
        if var:
            return safe_int(var.var_value)
        return default

    @staticmethod
    def get_long(name, default = None):
        var = Settings.search(var_name=name).first()
        if var:
            return long(var.var_value)
        return default

    @staticmethod
    def get_datetime(name, default=None):
        var = Settings.search(var_name=name).first()
        if var:
            try:
                return datetime.strptime(var.var_value, "%Y-%m-%dT%H:%M:%S.%f")
            except Exception, ex:
                logging.exception("Error parsing date [%s]", var.var_value)
        return default

