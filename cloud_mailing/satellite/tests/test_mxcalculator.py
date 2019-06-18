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

import logging
from ...common.unittest_mixins import DatabaseMixin

__author__ = 'ricard'

from twisted.trial import unittest
from twisted.internet import reactor

from ..mx import MXCalculator

#noinspection PyUnresolvedReferences
from zope.interface import Interface

from twisted.mail import smtp
from twisted.names import dns
from twisted.internet import defer
from twisted.internet import task
from twisted.internet.error import DNSLookupError, CannotListenError
from twisted.python import failure

import twisted.mail.mail
# import twisted.mail.maildir
import twisted.mail.relay
import twisted.mail.relaymanager
import twisted.mail.protocols
import twisted.mail.alias

from twisted.names.error import DNSNameError, DNSServerError
from twisted.names.dns import RRHeader, Record_CNAME, Record_MX

import twisted.cred.credentials
import twisted.cred.checkers
import twisted.cred.portal


from twisted.names import server
from twisted.names import client
from twisted.names import common

class TestAuthority(common.ResolverBase):
    def __init__(self):
        common.ResolverBase.__init__(self)
        self.addresses = {}

    def _lookup(self, name, cls, type, timeout = None):
        if name in self.addresses and type == dns.MX:
            results = []
            for a in self.addresses[name]:
                hdr = dns.RRHeader(
                    name, dns.MX, dns.IN, 60, dns.Record_MX(0, a)
                )
                results.append(hdr)
            return defer.succeed((results, [], []))
        return defer.fail(failure.Failure(dns.DomainError(name)))


def setUpDNS(self):
    self.auth = TestAuthority()
    factory = server.DNSServerFactory([self.auth])
    protocol = dns.DNSDatagramProtocol(factory)
    portNumber = 0
    while 1:
        #noinspection PyUnresolvedReferences
        self.port = reactor.listenTCP(0, factory, interface='127.0.0.1')
        portNumber = self.port.getHost().port

        try:
            #noinspection PyUnresolvedReferences
            self.udpPort = reactor.listenUDP(portNumber, protocol, interface='127.0.0.1')
        except CannotListenError:
            self.port.stopListening()
        else:
            break
    self.resolver = client.Resolver(servers=[('127.0.0.1', portNumber)])


def tearDownDNS(self):
    dl = [defer.maybeDeferred(self.port.stopListening), defer.maybeDeferred(self.udpPort.stopListening)]
    if hasattr(self.resolver, 'protocol') and self.resolver.protocol.transport is not None:
        dl.append(defer.maybeDeferred(self.resolver.protocol.transport.stopListening))
    #noinspection PyBroadException
    try:
        self.resolver._parseCall.cancel()
    except:
        pass
    return defer.DeferredList(dl)

class MXTestCase(unittest.TestCase):
    """
    Tests for L{mailing.mailing_sender.MXCalculator}.
    """
    def setUp(self):
        # self.connect_to_db()
        logging.getLogger('mx_calc').setLevel(logging.CRITICAL)
        setUpDNS(self)
        self.clock = task.Clock()
        self.mx = MXCalculator(self.resolver, self.clock)

    def tearDown(self):
        # return tearDownDNS(self).addBoth(lambda x: self.disconnect_from_db())
        return tearDownDNS(self)


    def test_defaultClock(self):
        """
        L{MXCalculator}'s default clock is C{twisted.internet.reactor}.
        """
        self.assertIdentical(
            MXCalculator(self.resolver).clock,
            reactor)


    def testSimpleSuccess(self):
        self.auth.addresses[b'test.domain'] = [b'the.email.test.domain']
        return self.mx.getMX('test.domain').addCallback(self._cbSimpleSuccess)

    def _cbSimpleSuccess(self, mxs):
        self.assertEqual(1, len(mxs))
        self.assertEqual(mxs[0].preference, 0)
        self.assertEqual(str(mxs[0].name), 'the.email.test.domain')

    def testSimpleFailure(self):
        self.mx.fallbackToDomain = False
        return self.assertFailure(self.mx.getMX('test.domain'), IOError)

    def testSimpleFailureWithFallback(self):
        return self.assertFailure(self.mx.getMX('test.domain'), DNSLookupError)


    def _exchangeTest(self, domain, records, correctMailExchange):
        """
        Issue an MX request for the given domain and arrange for it to be
        responded to with the given records.  Verify that the resulting mail
        exchange is the indicated host.

        @type domain: C{str}
        @type records: C{list} of L{RRHeader}
        @type correctMailExchange: C{str}
        @rtype: L{Deferred}
        """
        class DummyResolver(object):
            def lookupMailExchange(self, name):
                if name == domain:
                    return defer.succeed((
                        records,
                        [],
                        []))
                return defer.fail(DNSNameError(domain))

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX(domain)
        def gotMailExchange(records):
            self.assertEqual(str(records[0].name), correctMailExchange)
        d.addCallback(gotMailExchange)
        return d


    def test_mailExchangePreference(self):
        """
        The MX record with the lowest preference is returned by
        L{MXCalculator.getMX}.
        """
        domain = "example.com"
        good = "good.example.com"
        bad = "bad.example.com"

        records = [
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(1, bad)),
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(0, good)),
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(2, bad))]
        return self._exchangeTest(domain, records, good)


    def test_badExchangeExcluded(self):
        """
        L{MXCalculator.getMX} returns the MX record with the lowest preference
        which is not also marked as bad.
        """
        domain = "example.com"
        good = "good.example.com"
        bad = "bad.example.com"

        records = [
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(0, bad)),
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(1, good))]
        self.mx.markBad(bad)
        return self._exchangeTest(domain, records, good)


    def test_fallbackForAllBadExchanges(self):
        """
        L{MXCalculator.getMX} returns the MX record with the lowest preference
        if all the MX records in the response have been marked bad.
        """
        domain = "example.com"
        bad = "bad.example.com"
        worse = "worse.example.com"

        records = [
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(0, bad)),
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(1, worse))]
        self.mx.markBad(bad)
        self.mx.markBad(worse)
        return self._exchangeTest(domain, records, bad)


    def test_badExchangeExpires(self):
        """
        L{MXCalculator.getMX} returns the MX record with the lowest preference
        if it was last marked bad longer than L{MXCalculator.timeOutBadMX}
        seconds ago.
        """
        domain = "example.com"
        good = "good.example.com"
        previouslyBad = "bad.example.com"

        records = [
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(0, previouslyBad)),
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(1, good))]
        self.mx.markBad(previouslyBad)
        self.clock.advance(self.mx.timeOutBadMX)
        return self._exchangeTest(domain, records, previouslyBad)


    def test_goodExchangeUsed(self):
        """
        L{MXCalculator.getMX} returns the MX record with the lowest preference
        if it was marked good after it was marked bad.
        """
        domain = "example.com"
        good = "good.example.com"
        previouslyBad = "bad.example.com"

        records = [
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(0, previouslyBad)),
            RRHeader(name=domain,
                     type=Record_MX.TYPE,
                     payload=Record_MX(1, good))]
        self.mx.markBad(previouslyBad)
        self.mx.markGood(previouslyBad)
        self.clock.advance(self.mx.timeOutBadMX)
        return self._exchangeTest(domain, records, previouslyBad)


    def test_successWithoutResults(self):
        """
        If an MX lookup succeeds but the result set is empty,
        L{MXCalculator.getMX} should try to look up an I{A} record for the
        requested name and call back its returned Deferred with that
        address.
        """
        ip = '1.2.3.4'
        domain = 'example.org'

        class DummyResolver(object):
            """
            Fake resolver which will respond to an MX lookup with an empty
            result set.

            @ivar mx: A dictionary mapping hostnames to three-tuples of
                results to be returned from I{MX} lookups.

            @ivar a: A dictionary mapping hostnames to addresses to be
                returned from I{A} lookups.
            """
            mx = {domain: ([], [], [])}
            a = {domain: ip}

            def lookupMailExchange(self, domain):
                return defer.succeed(self.mx[domain])

            def getHostByName(self, domain):
                return defer.succeed(self.a[domain])

        self.mx.resolver = DummyResolver()
        self.mx.fallbackToDomain = True
        d = self.mx.getMX(domain)
        d.addCallback(self.assertEqual, [Record_MX(name=ip)])
        return d


    def test_failureWithSuccessfulFallback(self):
        """
        Test that if the MX record lookup fails, fallback is enabled, and an A
        record is available for the name, then the Deferred returned by
        L{MXCalculator.getMX} ultimately fires with a Record_MX instance which
        gives the address in the A record for the name.
        """
        class DummyResolver(object):
            """
            Fake resolver which will fail an MX lookup but then succeed a
            getHostByName call.
            """
            def lookupMailExchange(self, domain):
                return defer.fail(DNSNameError())

            def getHostByName(self, domain):
                return defer.succeed("1.2.3.4")

        self.mx.resolver = DummyResolver()
        self.mx.fallbackToDomain = True
        d = self.mx.getMX("domain")
        d.addCallback(self.assertEqual, [Record_MX(name="1.2.3.4")])
        return d


    def test_cnameWithoutGlueRecords(self):
        """
        If an MX lookup returns a single CNAME record as a result, MXCalculator
        will perform an MX lookup for the canonical name indicated and return
        the MX record which results.
        """
        alias = "alias.example.com"
        canonical = "canonical.example.com"
        exchange = "mail.example.com"

        class DummyResolver(object):
            """
            Fake resolver which will return a CNAME for an MX lookup of a name
            which is an alias and an MX for an MX lookup of the canonical name.
            """
            def lookupMailExchange(self, domain):
                if domain == alias:
                    return defer.succeed((
                        [RRHeader(name=domain,
                                  type=Record_CNAME.TYPE,
                                  payload=Record_CNAME(canonical))],
                        [], []))
                elif domain == canonical:
                    return defer.succeed((
                        [RRHeader(name=domain,
                                  type=Record_MX.TYPE,
                                  payload=Record_MX(0, exchange))],
                        [], []))
                else:
                    return defer.fail(DNSNameError(domain))

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX(alias)
        d.addCallback(lambda results: results[0])
        d.addCallback(self.assertEqual, Record_MX(name=exchange))
        return d


    def test_cnameChain(self):
        """
        If L{MXCalculator.getMX} encounters a CNAME chain which is longer than
        the length specified, the returned L{Deferred} should errback with
        L{CanonicalNameChainTooLong}.
        """
        class DummyResolver(object):
            """
            Fake resolver which generates a CNAME chain of infinite length in
            response to MX lookups.
            """
            chainCounter = 0

            def lookupMailExchange(self, domain):
                self.chainCounter += 1
                name = 'x-%d.example.com' % (self.chainCounter,)
                return defer.succeed((
                    [RRHeader(name=domain,
                              type=Record_CNAME.TYPE,
                              payload=Record_CNAME(name))],
                    [], []))

        cnameLimit = 3
        self.mx.resolver = DummyResolver()
        d = self.mx.getMX("mail.example.com", cnameLimit)
        self.assertFailure(
            d, twisted.mail.relaymanager.CanonicalNameChainTooLong)
        def cbChainTooLong(error):
            self.assertEqual(error.args[0], Record_CNAME("x-%d.example.com" % (cnameLimit + 1,)))
            self.assertEqual(self.mx.resolver.chainCounter, cnameLimit + 1)
        d.addCallback(cbChainTooLong)
        return d


    def test_cnameWithGlueRecords(self):
        """
        If an MX lookup returns a CNAME and the MX record for the CNAME, the
        L{Deferred} returned by L{MXCalculator.getMX} should be called back
        with the name from the MX record without further lookups being
        attempted.
        """
        lookedUp = []
        alias = "alias.example.com"
        canonical = "canonical.example.com"
        exchange = "mail.example.com"

        class DummyResolver(object):
            def lookupMailExchange(self, domain):
                if domain != alias or lookedUp:
                    # Don't give back any results for anything except the alias
                    # or on any request after the first.
                    return [], [], []
                return defer.succeed((
                    [RRHeader(name=alias,
                              type=Record_CNAME.TYPE,
                              payload=Record_CNAME(canonical)),
                     RRHeader(name=canonical,
                              type=Record_MX.TYPE,
                              payload=Record_MX(name=exchange))],
                    [], []))

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX(alias)
        d.addCallback(lambda results: results[0])
        d.addCallback(self.assertEqual, Record_MX(name=exchange))
        return d


    def test_cnameLoopWithGlueRecords(self):
        """
        If an MX lookup returns two CNAME records which point to each other,
        the loop should be detected and the L{Deferred} returned by
        L{MXCalculator.getMX} should be errbacked with L{CanonicalNameLoop}.
        """
        firstAlias = "cname1.example.com"
        secondAlias = "cname2.example.com"

        class DummyResolver(object):
            def lookupMailExchange(self, domain):
                return defer.succeed((
                    [RRHeader(name=firstAlias,
                              type=Record_CNAME.TYPE,
                              payload=Record_CNAME(secondAlias)),
                     RRHeader(name=secondAlias,
                              type=Record_CNAME.TYPE,
                              payload=Record_CNAME(firstAlias))],
                    [], []))

        self.mx.resolver = DummyResolver()
        d = self.mx.getMX(firstAlias)
        self.assertFailure(d, twisted.mail.relaymanager.CanonicalNameLoop)
        return d


    def testManyRecords(self):
        self.auth.addresses[b'test.domain'] = [
            b'mx1.test.domain', b'mx2.test.domain', b'mx3.test.domain'
        ]
        return self.mx.getMX('test.domain'
        ).addCallback(self._cbManyRecordsSuccessfulLookup
        )

    def _cbManyRecordsSuccessfulLookup(self, mxs):
        self.assertEqual(3, len(mxs))
        for mx in mxs:
            self.assertTrue(str(mx.name).split('.', 1)[0] in ('mx1', 'mx2', 'mx3'))
        self.mx.markBad(str(mxs[0].name))
        return self.mx.getMX('test.domain'
        ).addCallback(self._cbManyRecordsDifferentResult, mxs[0]
        )

    def _cbManyRecordsDifferentResult(self, nextMXs, mx):
        self.assertEqual(2, len(nextMXs))
        self.assertNotEqual(str(mx.name), str(nextMXs[0].name))
        self.mx.markBad(str(nextMXs[0].name))

        return self.mx.getMX('test.domain'
        ).addCallback(self._cbManyRecordsLastResult, mx, nextMXs[0]
        )

    def _cbManyRecordsLastResult(self, lastMXs, mx, nextMX):
        self.assertEqual(1, len(lastMXs))
        self.assertNotEqual(str(mx.name), str(lastMXs[0].name))
        self.assertNotEqual(str(nextMX.name), str(lastMXs[0].name))

        self.mx.markBad(str(lastMXs[0].name))
        self.mx.markGood(str(nextMX.name))

        return self.mx.getMX('test.domain'
        ).addCallback(self._cbManyRecordsRepeatSpecificResult, nextMX
        )

    def _cbManyRecordsRepeatSpecificResult(self, againMXs, nextMX):
        self.assertEqual(1, len(againMXs))
        self.assertEqual(str(againMXs[0].name), str(nextMX.name))


    def test_serverFailure(self):
        """
        Test that if the MX record lookup fails, fallback is enabled, and an A
        record is available for the name, then the Deferred returned by
        L{MXCalculator.getMX} ultimately fires with a Record_MX instance which
        gives the address in the A record for the name.
        """
        class DummyResolver(object):
            """
            Fake resolver which will fail an MX lookup but then succeed a
            getHostByName call.
            """
            def lookupMailExchange(self, domain):
                return defer.fail(DNSServerError())

            def getHostByName(self, domain):
                return defer.fail(DNSServerError())

        self.mx.resolver = DummyResolver()
        return self.assertFailure(self.mx.getMX("domain"), DNSServerError)




