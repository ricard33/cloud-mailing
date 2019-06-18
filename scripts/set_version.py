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
import sys

__author__ = 'Cedric RICARD'


def put_version(repo_path, target_path):
    import subprocess
    label = subprocess.check_output(["git", "describe"], cwd=repo_path).strip()
    stats = subprocess.check_output(['git', 'diff', '--shortstat'], cwd=repo_path)
    dirty = len(stats) > 0 and stats[-1]
    version = label + (dirty and "-dirty" or "")
    print (version)
    with open(os.path.join(target_path, 'version.properties'), 'wt') as f:
        f.write('VERSION=%s\n' % version)


if __name__ == '__main__':
    put_version(sys.argv[1], sys.argv[2])
