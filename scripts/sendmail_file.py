#!/usr/bin/env python
import argparse
import email
import email.parser
import email.utils
import smtplib
import dns.resolver

import sys


def prompt(prompt):
    return raw_input(prompt).strip()


def send_mail(serverIp, port, mailfrom, to, content):
    server = smtplib.SMTP(serverIp, port)
    server.set_debuglevel(1)
    server.sendmail(mailfrom, [to], content)
    server.quit()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Send email from RFC822 file.')
    parser.add_argument('-s', '--server', default=None, help='Target SMTP server. If none provided, will resolve real target using DNS.')
    parser.add_argument('-p', '--port', type=int, default=25, help='port number for SMTP (default: 25)')
    parser.add_argument('recipient', help="email recipient")
    parser.add_argument('filename', help="email content (should be rfc822 compliant)")

    args = parser.parse_args()

    to = args.recipient
    filename = args.filename
    msg_str = file(filename, 'rt').read()

    parser = email.parser.HeaderParser()
    header = parser.parsestr(msg_str)
    fromaddr = header["From"]
    # to = email.utils.parseaddr(header["To"])
    serverIp = args.server
    if not args.server:
        domain = to.split('@', 1)[1]
        print "Query MX for doamin '%s'" % domain
        answers = dns.resolver.query(domain, 'MX')
        for rdata in answers:
            print 'Host', rdata.exchange, 'has preference', rdata.preference
        serverIp = str(answers[0].exchange)
    print "Message length is " + repr(len(msg_str))

    send_mail(serverIp=serverIp, port= args.port, mailfrom=fromaddr, to=to, content=msg_str)
