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

import argparse
import email
import email.parser
import email.utils
import smtplib
import dns.resolver

import sys


def prompt(prompt):
    return input(prompt).strip()


def send_mail(serverIp, port, mailfrom, to, content, user=None, password=None):
    server = smtplib.SMTP(serverIp, port)
    server.set_debuglevel(1)
    if user:
        server.starttls()
        server.login(user, password)
    server.sendmail(mailfrom, [to], content)
    server.quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Send email from RFC822 file.')
    parser.add_argument('-s', '--server', default=None, help='Target SMTP server. If none provided, will resolve real target using DNS.')
    parser.add_argument('-p', '--port', type=int, default=25, help='port number for SMTP (default: 25)')
    parser.add_argument('-u', '--user', default=None, help='Username for authentication (unauthenticated session will be used if not provided)')
    parser.add_argument('-w', '--password', default=None, help='Password for authentication')
    parser.add_argument('recipient', help="email recipient")
    parser.add_argument('filename', help="email content (should be rfc822 compliant)")

    args = parser.parse_args()

    to = args.recipient
    filename = args.filename
    msg_bytes = b'\r\n'.join(open(filename, 'rb').read().splitlines())  # ensure to have CR/LF end line
    print(msg_bytes)

    parser = email.parser.BytesHeaderParser()
    header = parser.parsebytes(msg_bytes)
    fromaddr = header["From"]
    # to = email.utils.parseaddr(header["To"])
    serverIp = args.server
    if not args.server:
        domain = to.split('@', 1)[1]
        print("Query MX for doamin '%s'" % domain)
        answers = dns.resolver.query(domain, 'MX')
        for rdata in answers:
            print('Host', rdata.exchange, 'has preference', rdata.preference)
        serverIp = str(answers[0].exchange)
    print("Message length is " + repr(len(msg_bytes)))

    send_mail(serverIp=serverIp, port= args.port, mailfrom=fromaddr, to=to, content=msg_bytes,
              user=args.user, password=args.password)
