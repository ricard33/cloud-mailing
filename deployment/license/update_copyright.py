#!/usr/bin/python
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

"""
This script attempts to add a header to each file in the given directory 
The header will be put the line after a Shebang (#!) if present.
If a line starting with a regular expression 'skip' is present as first line or after the shebang it will ignore that file.
If filename is given only files matchign the filename regex will be considered for adding the license to,
by default this is '*'

usage: python addheader.py headerfile directory [filenameregex [dirregex [skip regex]]]

easy example: add header to all files in this directory:
python addheader.py licenseheader.txt . 

harder example adding someone as copyrightholder to all python files in a source directory,exept directories named 'includes' where he isn't added yet:
python addheader.py licenseheader.txt src/ ".*\.py" "^((?!includes).)*$" "#Copyright .* Jens Timmerman*" 
where licenseheader.txt contains '#Copyright 2012 Jens Timmerman'
"""
import os
import re
import sys

encoding_re = re.compile(r"coding[:=]\s*([-\w.]+)")

def writeheader(filename, header, skip=None):
    """
    write a header to filename, 
    skip files where first line after optional shebang matches the skip regex
    filename should be the name of the file to write to
    header should be a list of strings
    skip should be a regex
    """
    f = open(filename, "r")
    input_lines = f.readlines()
    f.close()
    output = []

    # comment out the next 3 lines if you don't wish to preserve shebangs
    if len(input_lines) > 0 and input_lines[0].startswith("#!"):
        output.append(input_lines[0])
        input_lines = input_lines[1:]

    if len(input_lines) > 0 and encoding_re.search(input_lines[0]):
        output.append(input_lines[0])
        input_lines = input_lines[1:]

    if skip and skip.match(input_lines[0]):  # skip matches, so skip this file
        return

    end_of_licence_token = 'If not, see <http://www.gnu.org/licenses/>'
    i = 0
    for line in input_lines[:30]:
        i += 1
        if end_of_licence_token in line:
            if header == input_lines[:i]:
                print "Header up-to-date on %s" % filename
                return
            input_lines = input_lines[i:]
            if input_lines and not input_lines[0].strip():
                input_lines = input_lines[1:]
            break

    output.extend(header)  # add the header
    output.append('\n')
    for line in input_lines:
        output.append(line)
    try:
        f = open(filename, 'w')
        f.writelines(output)
        f.close()
        print "added header to %s" % filename
    except IOError, err:
        print "something went wrong trying to add header to %s: %s" % (filename, err)


def addheader(directory, header, skip_reg, filename_reg, dir_regex):
    """
    recursively adds a header to all files in a dir
    arguments: see module docstring
    """
    listing = os.listdir(directory)
    # print "listing: %s " % listing
    # for each file/dir in this dir
    for i in listing:
        # get the full name, this way subsubdirs with the same name don't get ignored
        fullname = os.path.join(directory, i)
        if os.path.isdir(fullname):  # if dir, recursively go in
            if dir_regex.match(fullname):
                print "going into %s" % fullname
                addheader(fullname, header, skip_reg, filename_reg, dir_regex)
        else:
            if filename_reg.match(fullname):  # if file matches file regex, write the header
                writeheader(fullname, header, skip_reg)


def main(arguments=sys.argv):
    """
    main function: parses arguments and calls addheader
    """
    # argument parsing
    if len(arguments) > 6 or len(arguments) < 3:
        sys.stderr.write("Usage: %s header_file directory [filename_regex [dir_regex [skip regex]]]\n" \
                         "Hint: '.*' is a catch all regex\nHint:'^((?!regexp).)*$' negates a regex\n" % sys.argv[0])
        sys.exit(1)

    skip_reg = None
    file_regex = ".*"
    dir_regex = ".*"
    if len(arguments) > 5:
        skip_reg = re.compile(arguments[5])
    if len(arguments) > 3:
        file_regex = arguments[3]
    if len(arguments) > 4:
        dir_regex = arguments[4]
    # compile regex
    file_regex = re.compile(file_regex)
    dir_regex = re.compile(dir_regex)
    # read in the header_file just once
    header_file = open(arguments[1])
    header = header_file.readlines()
    header_file.close()
    addheader(arguments[2], header, skip_reg, file_regex, dir_regex)

# call the main method
script_dir = os.path.dirname(__file__)
base_dir = os.path.normpath(os.path.join(script_dir, '..', '..'))
# for folder in ['bin', 'common', 'config', 'deployment', 'master', 'satellite', 'scripts']
main(['', os.path.join(script_dir, 'license_header.txt'),
      os.path.join(base_dir, ),
      r'.+\.py$',
      r'^((?!.*/((\.svn)|(\.git)|(UT)|(_trial_temp.*)|(ssl)|(\.idea)|(log)|(temp))).)*$'])
