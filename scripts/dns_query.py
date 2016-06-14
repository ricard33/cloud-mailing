from sys import argv
from itertools import cycle
from pprint import pprint

import sys
from twisted.names import client
from twisted.internet.task import react
from twisted.internet.defer import gatherResults, inlineCallbacks

def query(reactor, server, name):
    # Create a new resolver that uses the given DNS server
    resolver = client.Resolver(
        resolv="/dev/null", servers=[(server, 53)], reactor=reactor)
    # Use it to do an MX request for the name
    return resolver.lookupMailExchange(name)

@inlineCallbacks
def main(reactor, *names):
    # Here's some random DNS servers to which to issue requests.
#     servers = ["192.168.168.31", "192.168.168.32"]
    servers = ["8.8.4.4", "8.8.8.8"]

    # Handy trick to cycle through those servers forever
    next_server = cycle(servers).next

    # Issue queries for all the names given, alternating between servers.
    results = []
    for n in names:
        results.append(query(reactor, next_server(), n))
    # Wait for all the results
    results = yield gatherResults(results)
    # And report them
    for name, result in (zip(names, results)):
        print("Request for '%s':" % name)
        for r in result[0]:
            print "   ", r.payload

if __name__ == '__main__':
    from twisted.python import log

    log.startLogging(sys.stdout)

    # Run the main program with the reactor going and pass names
    # from the command line arguments to be resolved
    react(main, argv[1:])