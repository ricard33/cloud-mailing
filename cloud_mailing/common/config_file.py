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

from ConfigParser import RawConfigParser

class ConfigFile(RawConfigParser):
    def get(self, section, option, default = None):
        if self.has_option(section, option) or default is None:
            return RawConfigParser.get(self, section, option)
        else:
            return default

    def getint(self, section, option, default = None):
        if self.has_option(section, option) or not isinstance(default, int):
            return RawConfigParser.getint(self, section, option)
        else:
            return default

    def getfloat(self, section, option, default = None):
        if self.has_option(section, option) or not isinstance(default, float):
            return RawConfigParser.getfloat(self, section, option)
        else:
            return default
        
    def getboolean(self, section, option, default = None):
        if self.has_option(section, option) or not isinstance(default, bool):
            return RawConfigParser.getboolean(self, section, option)
        else:
            return default

    def getlist(self, section, option, default = None):
        if self.has_option(section, option) or default is None:
            return RawConfigParser.get(self, section, option).split(',')
        else:
            return default

    def set(self, section, option, value = None):
        if not self.has_section(section):
            self.add_section(section)
        RawConfigParser.set(self, section, option, str(value))
