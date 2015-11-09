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

__author__ = 'ricard'

__product_version__ = "0.3.0"

def __read_version_from_properties_file():
    import os
    filename = os.path.join(os.path.dirname(__file__), 'version.properties')
    if os.path.exists(filename):
        with open(filename, 'rt') as f:
            for line in f:
                try:
                    name, value = line.split('=')
                    if name == 'VERSION':
                        return value.strip()
                except:
                    pass
    return __product_version__

__version__ = __read_version_from_properties_file()