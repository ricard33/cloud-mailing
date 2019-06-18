#!/usr/bin/env python
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



import random
import smtpd
import asyncore
import sys
import time
import threading
from datetime import datetime


class FakeSMTPChannel(smtpd.SMTPChannel):
    def smtp_RCPT(self, arg):
        """Overload to reject recipients with 'error' word in address."""
        if not self.seen_greeting:
            self.push('503 Error: send HELO first')
            return
        print('===> RCPT', arg, file=smtpd.DEBUGSTREAM)
        if not self.mailfrom:
            self.push('503 Error: need MAIL command')
            return
        syntaxerr = '501 Syntax: RCPT TO: <address>'
        if self.extended_smtp:
            syntaxerr += ' [SP <mail-parameters>]'
        if arg is None:
            self.push(syntaxerr)
            return
        arg = self._strip_command_keyword('TO:', arg)
        address, params = self._getaddr(arg)
        if not address:
            self.push(syntaxerr)
            return
        if 'error' in address:
            self.push('550 Unknown recipient %s' % address)
            return
        if not self.extended_smtp and params:
            self.push(syntaxerr)
            return
        self.rcpt_options = params.upper().split()
        params = self._getparams(self.rcpt_options)
        if params is None:
            self.push(syntaxerr)
            return
        # XXX currently there are no options we recognize.
        if len(params.keys()) > 0:
            self.push('555 RCPT TO parameters not recognized or not implemented')
            return
        self.rcpttos.append(address)
        print('recips:', self.rcpttos, file=smtpd.DEBUGSTREAM)
        self.push('250 OK')


class FakeSMTPD(smtpd.SMTPServer):
    def __init__(self, localaddr, remoteaddr):
        smtpd.SMTPServer.__init__(self, localaddr, remoteaddr)
        self.t0 = time.time()
        self.last_time = 0
        self.email_count = 0
        self.bandwidth = 0
        self.max_delay_before_reset = 600  # seconds
        self.lock = threading.Lock()
        self.d = {}
        
    def handle_accept(self):
        pair = self.accept()
        if pair is not None:
            conn, addr = pair
            print('Incoming connection from %s' % repr(addr))
            channel = FakeSMTPChannel(self, conn, addr)

    def process_message(self, peer, mailfrom, rcpttos, data, **kwargs):
        with self.lock:
            t1 = time.time()
            if t1 - self.last_time > self.max_delay_before_reset:
                print("Resetting Bandwidth statistics due to too high delay between messages.")
                self.t0 = t1 - 0.1  # to avoid a 'division by zero' error
                self.email_count = 0
                self.bandwidth = 0
            self.email_count += 1
            self.bandwidth += len(data)
            self.last_time = t1
            delta = t1 - self.t0
            if rcpttos[0] in self.d:
                self.d[rcpttos[0]] +=1
                print('[%s] %s received %d times' % (datetime.now(), rcpttos[0], self.d[rcpttos[0]]), file=sys.stderr)
            else:
                self.d[rcpttos[0]] = 1
            print('\r[%s] %d messages received into %d seconds. Rate = %.1f mails/s | %d mails/day  Bandwidth = %.1f Kb/s' % (
                datetime.now(), self.email_count, delta, self.email_count / delta, (self.email_count * 86400) / delta,
                (self.bandwidth / 1024.0) / delta))
        
if __name__ == "__main__":
    port = 25
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    # smtpd.DEBUGSTREAM = sys.stdout
    server = FakeSMTPD(("0.0.0.0", port), None)
    
    print("Fake SMTP server listening on port %d" % port)
    asyncore.loop()
    
