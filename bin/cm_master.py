#!/usr/bin/env python
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

import sys, os
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(__file__), '..')))

from cloud_mailing.master import master_main, cloud_master
from twisted.internet import reactor

if __name__ == '__main__':
    master_main.main()
    try:
        reactor.run()
    finally:
        print "Stop all threads"
        cloud_master.stop_all_threadpools()