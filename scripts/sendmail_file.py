#!/usr/bin/env python

import email
import email.parser
import email.utils
import smtplib
import dns.resolver

import sys


def prompt(prompt):
    return raw_input(prompt).strip()


def send_mail(serverIp, mailfrom, to, content):
    server = smtplib.SMTP(serverIp)
    server.set_debuglevel(1)
    server.sendmail(mailfrom, [to], content)
    server.quit()


if __name__ == '__main__':

    if len(sys.argv) != 3:
        print "Usage: %s recipient filename" % sys.argv[0]
    to = sys.argv[1]
    filename = sys.argv[2]
    msg_str = file(filename, 'rt').read()

    parser = email.parser.HeaderParser()
    header = parser.parsestr(msg_str)
    fromaddr = header["From"]
    # to = email.utils.parseaddr(header["To"])
    domain = to.split('@', 1)[1]
    print "Query MX for doamin '%s'" % domain
    answers = dns.resolver.query(domain, 'MX')
    for rdata in answers:
        print 'Host', rdata.exchange, 'has preference', rdata.preference
    serverIp = str(answers[0].exchange)

    print "Message length is " + repr(len(msg_str))

    send_mail(serverIp=serverIp, mailfrom=fromaddr, to=to, content=msg_str)
