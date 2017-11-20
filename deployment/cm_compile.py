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

import os, sys, re
from os.path import getsize, join
import py_compile

base_dirs = [join(".", x) for x in ('bin', 'cloud_mailing', )]
verbose = '-v' in sys.argv
delete_py = '--delete-py' in sys.argv
excludes = []  # don't visit .svn directories
exclude = re.compile("(/[.]svn)|(/nolimit)|(/commands)|(settings.py)")


def clean_pyc_files(base_dir):
    for root, dirs, files in os.walk(base_dir):
        for name in files:
            if name.endswith(".pyc") or name.endswith(".pyo"):
                fullpath = join(root, name)
                print("Deleting '%s'... " % fullpath, end=' ')
                os.remove(fullpath)
                print("Ok")
        for name in ('.svn', '.git', '.hg', '.env'):
            if name in dirs:
                dirs.remove(name)  # don't visit .svn, .git and .hg directories


def compile_python(base_dir):
    errors = []
    for root, dirs, files in os.walk(base_dir):
        for name in files:
            if name.endswith(".py"):
                fullpath = join(root, name).replace('\\', '/')
                if exclude.search(fullpath):
                    continue
                if verbose:
                    print("Compiling '%s'... " % fullpath, end=' ')
                try:
                    py_compile.compile(fullpath)
                    if delete_py:
                        os.remove(fullpath)
                    if verbose:
                        print("Ok")
                except Exception as ex:
                    if verbose:
                        print("ERROR: %s" % str(ex))
                    print("ERROR compiling '%s': %s" % (fullpath, str(ex)), file=sys.stderr)
                    errors.append((fullpath, ex))
        for d in excludes:
            if d in dirs:
                dirs.remove(d)
    return errors

if __name__ == "__main__":
    if '-c' in sys.argv:
        print("Removing all .pyc files...")
        for dir in base_dirs:
            clean_pyc_files(dir)
    else:
        errors = []
        for dir in base_dirs:
            errors.append(compile_python(dir))
        print()
        if len(errors):
            print("%d error(s) found!" % len(errors), file=sys.stderr)
        else:
            print("CloudMailing's files successfully compiled!")

        import compileall

        print("Compiling Python Libraries...")
        compileall.compile_path(True, 10)
        print("Finished!")
