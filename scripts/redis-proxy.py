#!/usr/bin/env python

import sys

from twisted.internet import defer
from twisted.internet import protocol
from twisted.internet import reactor
from twisted.python import log

class ProxyClientProtocol(protocol.Protocol):
    def connectionMade(self):
        log.msg('Client: connected to peer')
        self.cli_queue = self.factory.cli_queue
        self.cli_queue.get().addCallback(self.serverDataReceived)

    def serverDataReceived(self, chunk):
        if chunk is False:
            self.cli_queue = None
            log.msg(f'Client: disconnecting from peer')
            self.factory.continueTrying = False
            self.transport.loseConnection()
        elif self.cli_queue:
            log.msg(f'Client: writing {len(chunk)} bytes to peer')
            self.transport.write(chunk)
            self.cli_queue.get().addCallback(self.serverDataReceived)
        else:
            self.factory.cli_queue.put(chunk)

    def dataReceived(self, chunk):
        log.msg(f'Client: {len(chunk)} bytes received from peer')
        self.factory.srv_queue.put(chunk)

    def connectionLost(self, why):
        if self.cli_queue:
            self.cli_queue = None
            log.msg(f'Client: peer disconnected unexpectedly')


class ProxyClientFactory(protocol.ReconnectingClientFactory):
    maxDelay = 10
    continueTrying = True
    protocol = ProxyClientProtocol

    def __init__(self, srv_queue, cli_queue):
        self.srv_queue = srv_queue
        self.cli_queue = cli_queue

class ProxyServer(protocol.Protocol):
    def connectionMade(self):
        self.srv_queue = defer.DeferredQueue()
        self.cli_queue = defer.DeferredQueue()
        self.srv_queue.get().addCallback(self.clientDataReceived)
        self.cli_temp = ''

        self.factory = ProxyClientFactory(self.srv_queue, self.cli_queue)
        reactor.connectTCP("localhost", 6379, self.factory)

    def clientDataReceived(self, chunk):
        log.msg(f'Server: writing {len(chunk)} bytes to original client')
        data = chunk.decode('utf-8').strip()
        
        if 'MOVED' in data:
            (server, port) = data.split(' ')[2].split(':')
            
            log.msg(f'Client: Connection moved to {server}:{port}')
            reactor.connectTCP(server, int(port), self.factory)
            self.cli_queue.put(self.cli_temp)
        else:
            self.transport.write(chunk)

        self.srv_queue.get().addCallback(self.clientDataReceived)

    def dataReceived(self, chunk):
        self.cli_temp = chunk
        log.msg(f'Server: {len(chunk)} bytes received')
        self.cli_queue.put(chunk)

    def connectionLost(self, why):
        self.cli_queue.put(False)

if __name__ == "__main__":
    log.startLogging(sys.stdout)
    factory = protocol.Factory()
    factory.protocol = ProxyServer
    reactor.listenTCP(26379, factory, interface="0.0.0.0")
    reactor.run()