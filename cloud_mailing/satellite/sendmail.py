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
import os
import smtplib
import dns.resolver
from dns.exception import DNSException
from datetime import datetime
import logging

#import wingdbstub

#------------------------------------------------------------------------
# CM independent code
#------------------------------------------------------------------------

def mx_resolver(recipientOrDomain):
    """Helper function that do MX resolution and returning a sorted list of IPs.
    
    @param recipientOrDomain: can be a recipient email or only the right part (domain)
    of an email.
    """
    try:
        domain = recipientOrDomain.split('@')[1]
    except IndexError:
        domain = recipientOrDomain
    try:
        answers = [r for r in dns.resolver.query(domain, 'MX')]
        answers.sort()

        ips = []
        for name in answers:
            for ip in dns.resolver.query(name.exchange):
                ips.append(ip.address)
        return ips
    
    except DNSException, ex:
        logging.getLogger('sendmail').warning("Can't get MX record for domain '%s': %s" % (domain, str(ex)))
        raise
    

class EmailSender(smtplib.SMTP):

    def __init__(self, host = None, port = None, local_hostname = None):
        smtplib.SMTP.__init__(self, host, port, local_hostname)
        #self.set_debuglevel(100)

    def rset(self):
        """SMTP 'rset' command -- resets session."""
        try:
            return self.docmd("rset")
        except:
            pass
    
    def __sendmail(self, from_addr, to_addrs, msg, mail_options=[],
                 rcpt_options=[]):
        """This command performs an entire mail transaction.

        The arguments are:
            - from_addr    : The address sending this mail.
            - to_addrs     : A list of addresses to send this mail to.  A bare
                             string will be treated as a list with 1 address.
            - msg          : The message to send.
            - mail_options : List of ESMTP options (such as 8bitmime) for the
                             mail command.
            - rcpt_options : List of ESMTP options (such as DSN commands) for
                             all the rcpt commands.

        If there has been no previous EHLO or HELO command this session, this
        method tries ESMTP EHLO first.  If the server does ESMTP, message size
        and each of the specified options will be passed to it.  If EHLO
        fails, HELO will be tried and ESMTP options suppressed.

        This method will return normally if the mail is accepted for at least
        one recipient.  It returns a dictionary, with one entry for each
        recipient that was refused.  Each entry contains a tuple of the SMTP
        error code and the accompanying error message sent by the server.

        This method may raise the following exceptions:

         SMTPHeloError          The server didn't reply properly to
                                the helo greeting.
         SMTPRecipientsRefused  The server rejected ALL recipients
                                (no mail was sent).
         SMTPSenderRefused      The server didn't accept the from_addr.
         SMTPDataError          The server replied with an unexpected
                                error code (other than a refusal of
                                a recipient).

        Note: the connection will be open even after an exception is raised.

        Example:

         >>> import smtplib
         >>> s=smtplib.SMTP("localhost")
         >>> tolist=["one@one.org","two@two.org","three@three.org","four@four.org"]
         >>> msg = '''From: Me@my.org
         ... Subject: testin'...
         ...
         ... This is a test '''
         >>> s.sendmail("me@my.org",tolist,msg)
         { "three@three.org" : ( 550 ,"User unknown" ) }
         >>> s.quit()

        In the above example, the message was accepted for delivery to three
        of the four addresses, and one was rejected, with the error code
        550.  If all addresses are accepted, then the method will return an
        empty dictionary.

        """
        self.ehlo_or_helo_if_needed()
        esmtp_opts = []
        if self.does_esmtp:
            # Hmmm? what's this? -ddm
            # self.esmtp_features['7bit']=""
            if self.has_extn('size'):
                esmtp_opts.append("size=%d" % len(msg))
            for option in mail_options:
                esmtp_opts.append(option)

        (code,resp) = self.mail(from_addr, esmtp_opts)
        if code != 250:
            self.rset()
            raise smtplib.SMTPSenderRefused(code, resp, from_addr)
        senderrs={}
        if isinstance(to_addrs, basestring):
            to_addrs = [to_addrs]
        for each in to_addrs:
            (code,resp)=self.rcpt(each, rcpt_options)
            if (code != 250) and (code != 251):
                senderrs[each]=(code,resp)
        if len(senderrs)==len(to_addrs):
            # the server refused all our recipients
            self.rset()
            raise smtplib.SMTPRecipientsRefused(senderrs)
        (code,resp) = self.data(msg)
        if code != 250:
            self.rset()
            raise smtplib.SMTPDataError(code, resp)
        #if we got here then somebody got our mail
        return senderrs

#------------------------------------------------------------------------
# Using Twisted

from OpenSSL.SSL import SSLv3_METHOD

from twisted.mail.smtp import ESMTPClient, ESMTPSenderFactory, DNSNAME, Address
from twisted.internet.ssl import ClientContextFactory
from twisted.internet import defer
from twisted.internet import reactor, protocol, error
from twisted.mail import smtp
from twisted.python.failure import Failure

def sendmail_async(
    authenticationUsername, authenticationSecret,
    fromAddress, toAddress,
    messageFile,
    smtpHost, smtpPort=25
    ):
    """
    @param authenticationUsername: The username with which to authenticate.
    @param authenticationSecret: The password with which to authenticate.
    @param fromAddress: The SMTP reverse path (ie, MAIL FROM)
    @param toAddress: The SMTP forward path (ie, RCPT TO)
    @param messageFile: A file-like object containing the headers and body of
    the message to send.
    @param smtpHost: The MX host to which to connect.
    @param smtpPort: The port number to which to connect.

    @return: A Deferred which will be called back when the message has been
    sent or which will errback if it cannot be sent.
    """

    # Create a context factory which only allows SSLv3 and does not verify
    # the peer's certificate.
    contextFactory = ClientContextFactory()
    contextFactory.method = SSLv3_METHOD

    resultDeferred = defer.Deferred()

    senderFactory = ESMTPSenderFactory(
        authenticationUsername,
        authenticationSecret,
        fromAddress,
        toAddress,
        messageFile,
        resultDeferred,
        contextFactory=contextFactory,
        heloFallback=True,
        requireTransportSecurity=False,
        requireAuthentication=False)

    #pylint: disable-msg=E1101
    s = reactor.connectTCP(smtpHost, smtpPort, senderFactory)
    #pylint: enable-msg=E1101
    
    def close_socket(d):
        s.disconnect()
        return d

    return resultDeferred.addBoth(close_socket)


class RelayerMixin:
    """
    Add relayer capability to an SMTPClient taking emails from its factory.
    """

    #def _removeDeferred(self, argh):
        #del self.result
        #return argh

    def getMailFrom(self):
        """Return the email address the mail is from."""
        logging.getLogger("sendmail").debug("[%s] Calling getMailFrom for '%s'", 
                                            self.factory.targetDomain, self.transport.getPeer())
                                            
        n = self.factory.getNextEmail()
        if n:
            fromEmail, toEmails, filename, deferred = n
            if not os.path.exists(filename):
                # content is removed from disk as soon as the mailing is closed
                raise smtp.SMTPClientError(471, "Sending aborted. Mailing stopped.")
            self.fromEmail = fromEmail
            self.toEmails = toEmails
            self.mailFile = open(filename, 'rt')
            self.result = deferred
            #WHY? self.result.addBoth(self._removeDeferred)
            return str(self.fromEmail)
        return None

    def getMailTo(self):
        """Return a list of emails to send to."""
        return self.toEmails

    def getMailData(self):
        """Return file-like object containing data of message to be sent.

        Lines in the file should be delimited by '\\n'.
        """
        # Rewind the file in case part of it was read while attempting to
        # send the message.
        if not os.path.exists(self.mailFile.name):
            # content is removed from disk as soon as the mailing is closed
            raise smtp.SMTPClientError(471, "Sending aborted. Mailing stopped.")
        self.mailFile.seek(0, 0)
        return self.mailFile

    def sendError(self, exc):
        """
        If an error occurs before a mail message is sent sendError will be
        called.  This base class method sends a QUIT if the error is
        non-fatal and disconnects the connection.

        @param exc: The SMTPClientError (or child class) raised
        @type exc: C{SMTPClientError}
        """
        logging.getLogger("sendmail").error("sendError: %s", exc)
        if isinstance(exc, smtp.SMTPClientError) and not exc.isFatal:
            self._disconnectFromServer()
        else:
            # If the error was fatal then the communication channel with the
            # SMTP Server is broken so just close the transport connection
            self.smtpState_disconnect(-1, None)
        
        if hasattr(self, 'mailFile') and self.mailFile:
            self.mailFile.close()
            self.mailFile = None
        if hasattr(self, 'result'):
            self.result.errback(exc)

    def sentMail(self, code, resp, numOk, addresses, log):
        """Called when an attempt to send an email is completed.

        If some addresses were accepted, code and resp are the response
        to the DATA command. If no addresses were accepted, code is -1
        and resp is an informative message (NO that's wrong, this is the 
        last returned code).

        @param code: the code returned by the SMTP Server
        @param resp: The string response returned from the SMTP Server
        @param numOK: the number of addresses accepted by the remote host.
        @param addresses: is a list of tuples (address, code, resp) listing
                          the response to each RCPT command.
        @param log: is the SMTP session log
        """
        if hasattr(self, 'mailFile') and self.mailFile:
            self.mailFile.close()
            self.mailFile = None
        # Do not retry, the SMTP server acknowledged the request
        if code not in smtp.SUCCESS:
            errlog = []
            for addr, acode, aresp in addresses:
                if acode not in smtp.SUCCESS:
                    errlog.append("%s: %03d %s" % (str(addr), acode, aresp))

            errlog.append(log.str())
            #print '\n'.join(errlog)
            log.clear()
            exc = smtp.SMTPDeliveryError(code, resp, '\n'.join(errlog), addresses)
            self.result.errback(Failure(exc))
        else:
            log.clear()
            self.result.callback((numOk, addresses))

    def connectionLost(self, reason=protocol.connectionDone):
        """We are no longer connected"""
        ## Taken from SMTPClient
        self.setTimeout(None)
        if hasattr(self, 'mailFile') and self.mailFile:
            self.mailFile.close()
            self.mailFile = None
        ## end of SMTPClient
        # Disconnected after a QUIT command -> normal case
        logging.getLogger("sendmail").debug("[%s] Disconnected from '%s'",
                                            self.factory.targetDomain, self.transport.getPeer())
        self.factory._lastLogOnConnectionLost = self.log.str()

class SMTPRelayer(RelayerMixin, ESMTPClient):
    """
    SMTP protocol that sends a set of emails based on information it 
    gets from its factory, a L{SMTPSenderFactory}.
    """

class SMTPRelayerFactory(protocol.ClientFactory):
    """
    Utility factory for sending mailings easily. 
    Will try to send all emails using the same connection.
    
    """

    domain = DNSNAME
    protocol = SMTPRelayer

    def __init__(self, targetDomain, retries=5, timeout=60,
                 contextFactory=None, heloFallback=True,
                 requireAuthentication=False,
                 requireTransportSecurity=False,
                 logger=None,
                 username=None, secret=None,
                 connectionClosedCallback=None,
                 connectionFailureErrback=None):
        """
        @param targetDomain: All emails handled by this factory will be 
        handled by a simple SMTP server: the one specified as MX record 
        for this domain name.
    
        @param retries: The number of times to retry delivery of this
        message.

        @param timeout: Period, in seconds, for which to wait for
        server responses, or None to wait forever.
        """
        assert isinstance(retries, (int, long))

        self.targetDomain = targetDomain

        self._contextFactory = contextFactory
        self._heloFallback = heloFallback
        self._requireAuthentication = requireAuthentication
        self._requireTransportSecurity = requireTransportSecurity
        self._username=username
        self._secret=secret
        self._connectionFailureErrback = connectionFailureErrback
        self._connectionClosedCallback = connectionClosedCallback
        self._dateStarted = datetime.now()
        self._lastLogOnConnectionLost = ""    # Used to track message returned by server in case of early rejection (before EHLO)

        self.retries = -retries
        self.timeout = timeout
        
        self.mails = []
        self.last_email = None
        self.deferred = defer.Deferred()
        self.log = logger or logging.getLogger("sendmail")

    def __repr__(self):
        return "<%s.%s instance for '%s' at 0x%x>" % (self.__module__, self.__class__.__name__, 
                                                      self.targetDomain, id(self))
        
    def __unicode__(self):
        return u"<%s.%s instance for '%s' at 0x%x>" % (self.__module__, self.__class__.__name__, 
                                                       self.targetDomain, id(self))

    @property
    def startDate(self):
        return self._dateStarted
    
    def startedConnecting(self, connector):
        """Called when a connection has been started.

        You can call connector.stopConnecting() to stop the connection attempt.

        @param connector: a Connector object.
        """
        self.log.debug("[%s] SMTP Connection started on '%s'...", self.targetDomain, connector.getDestination())

    def clientConnectionFailed(self, connector, err):
        """Called when a connection has failed to connect.

        It may be useful to call connector.connect() - this will reconnect.

        @type reason: L{twisted.python.failure.Failure}
        """
        self.log.warn("[%s] SMTP Connection failed for '%s': %s", self.targetDomain, connector.getDestination(), str(err.value).decode(encoding='utf-8', errors='replace'))
        self._processConnectionError(connector, err)

    def clientConnectionLost(self, connector, err):
        """Called when an established connection is lost.

        It may be useful to call connector.connect() - this will reconnect.

        @type reason: L{twisted.python.failure.Failure}
        """
        if self.last_email == None and len(self.mails) == 0 and err.check(error.ConnectionDone):
            self.log.debug("[%s] SMTP Connection done for '%s'.", self.targetDomain, connector.getDestination())
            if self._connectionClosedCallback:
                self._connectionClosedCallback(connector)
            return
        self.log.warn("[%s] SMTP Connection lost for '%s': %s", self.targetDomain, connector.getDestination(), err.value)
        self._processConnectionError(connector, err)

    def _processConnectionError(self, connector, err):
        if self.retries < 0:
            self.log.info("[%s] SMTP Client retrying server '%s'. Retry: %s", self.targetDomain, connector.getDestination(), -self.retries)
            connector.connect()
            self.retries += 1
        else:
            if self._connectionFailureErrback:
                self._connectionFailureErrback(connector, err)
        
    def stopFactory(self):
        """This will be called before I stop listening on all Ports/Connectors.

        This can be overridden to perform 'shutdown' tasks such as disconnecting
        database connections, closing files, etc.

        It will be called, for example, before an application shuts down,
        if it was connected to a port. User code should not call this function
        directly.
        """
        self.log.debug("[%s] Stopping relay factory.", self.targetDomain)
        if self.deferred:
            if len(self.mails) > 0 or self.last_email:
                self.deferred.errback(Failure(smtp.SMTPConnectError(-1, self._lastLogOnConnectionLost or "Connection closed prematurely.")))
            else:
                self.deferred.callback(self.targetDomain)
            self.deferred = None   # to avoid another call
        
    def buildProtocol(self, addr):
        self.log.debug("[%s] BuildProtocol for ip '%s'.", self.targetDomain, addr)
        p = self.protocol(secret=self._secret, contextFactory=None, identity=self.domain, logsize=len(self.mails)*2+2)
        p.debug = True  # to enable SMTP log
        p.heloFallback = self._heloFallback
        p.requireAuthentication = self._requireAuthentication
        p.requireTransportSecurity = self._requireTransportSecurity
        p.factory = self
        p.timeout = self.timeout
        if self._username:
            from twisted.mail.imap4 import CramMD5ClientAuthenticator, LOGINAuthenticator
            p.registerAuthenticator(CramMD5ClientAuthenticator(self._username))
            p.registerAuthenticator(LOGINAuthenticator(self._username))
            p.registerAuthenticator(smtp.PLAINAuthenticator(self._username))
        return p

    def send_email(self, fromEmail, toEmails, fileName):
        """
        @param fromEmail: The RFC 2821 address from which to send this
        message.

        @param toEmails: A sequence of RFC 2821 addresses to which to
        send this message.

        @param fileName: A full path to the file containing the message to send.

        @param deferred: A Deferred to callback or errback when sending
        of this message completes.
        """
        deferred = defer.Deferred()
        self.log.debug("Add %s into factory (%s)", ', '.join(toEmails), self.targetDomain)
        self.mails.insert(0, (Address(fromEmail), map(Address, toEmails), fileName, deferred))
        return deferred
    
    def getNextEmail(self):
        try:
            self.last_email = self.mails.pop()
            self.log.debug("Factory (%s) return next email: %s", self.targetDomain, self.last_email[1])
            return self.last_email
        except IndexError:
            self.log.debug("Factory (%s) return next email: EMPTY", self.targetDomain)
            self.last_email = None
            #self.deferred.callback(self.targetDomain) 
            return None

    def get_recipients_count(self):
        return len(self.mails)
        
