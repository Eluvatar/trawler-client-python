#    Copyright 2013 Eluvatar
#
#    This file is part of Trawler.
#
#    Trawler is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Trawler is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Trawler.  If not, see <http://www.gnu.org/licenses/>.
"""
  This module implements the Trawler client interface. Do not import
  this module directly, import the 'trawler' module instead.
"""

import trawler_pb2 as protocol

import zmq
import threading
from Queue import Queue
from collections import namedtuple

def is_open(tsock):
    return not tsock.closed

class Connection(object):
    """
    A connection to a Trawler daemon. Has a worker thread which owns
    all interaction with the zmq socket pointed at said daemon.
    """
    def __init__(self, host, port, user_agent_str):
        self.url = "tcp://{0}:{1}".format(host, port)
        self.user_agent = user_agent_str
        self.req_id = 0
        self.req_id_lock = threading.Lock()
        self.callbacks = dict()
        self.opening = threading.Event()
        self.queue = Queue()
        self.ack_callbacks = dict()
        tname = "Connection {0} worker".format(id(self))
        thread = threading.Thread(name=tname, target=self.worker)
        thread.daemon = True
        thread.start()

    def worker(self):
        qsock = zmq.Context.instance().socket(zmq.PULL)
        qsock.bind("inproc://request_queue-"+str(id(self)))
        poller = zmq.Poller()
        tsock = zmq.Context.instance().socket(zmq.REQ)
        poller.register(tsock, zmq.POLLIN)
        poller.register(qsock, zmq.POLLIN)
        while(True):
            self.opening.wait()
            self.open(tsock)
            while is_open(tsock):
                socks = dict(poller.poll())
                if qsock in socks and socks[qsock] == zmq.POLLIN:
                    qsock.recv()
                    while not self.queue.empty():
                        (todo, args, kwargs) = self.queue.get_nowait()
                        todo(*args, **kwargs)
                        self.queue.task_done()
                if tsock in socks and socks[tsock] == zmq.POLLIN:
                    self.receive(tsock)
            self.opening.clear()

    assert(protocol.Reply.Response == 0)
    assert(protocol.Reply.Ack == 1) 
    assert(protocol.Reply.Nack == 2)
    def receive(self, tsock):
        reply = protocol.Reply.ParseFromString(tsock.recv())
        if( reply.reply_type < 0 or reply.reply_type > 2 ):
            self.invalid(reply)
            return
        [ self.response, self.ack, self.nack ][reply.reply_type](reply)

    def ack(self, reply):
        self.ack_callbacks[reply.req_id](reply.result)
        del self.ack_callbacks[reply.req_id]

    def nack(self, reply):
        self.ack(self, reply)
        self.callbacks[reply.req_id](Response(result=reply.result))
        del self.callbacks[reply.req_id]

    def response(self, reply):
        msg = tsock.multipart()
        req_id = reply.req_id
        if reply.headers:
            response = reply.headers + reply.response
        else:
            response = reply.response
        self.callbacks[req_id](Response(result=reply.result, response=response))
        del self.callbacks[req_id]

    def invalid(self, reply):
        #TODO handle failure -- perhaps call all callbacks with an
        # invalid object and raise exception, killing worker thread?
        pass

    def require_open(dep_fn):
        def impl_fn(*args, **kwargs):
            self=args[0]
            self.opening.set()
            dep_fn(*args, **kwargs)
        return impl_fn

    def open(self, tsock):
        tsock.connect(self.url)

    def enqueue(self, qfn):
        done = threading.Event()
        ret = []
        def impl_fn(tsock):
            ret[0] = qfn(tsock)
            done.set()
        self.queue.put(impl_fn)
        qsock = zmq.Context.instance().socket(zmq.PUSH)
        qsock.connect("inproc://request_queue-"+str(id(self)))
        qsock.send("")
        done.wait()
        return ret[0]

    def is_open(self):
        return self.enqueue(is_open)

    def __nonzero__(self):
        return self.is_open()

    @require_open
    def request_async(self, callback, method, path, query=None,
                      session=None, headers=False):
        done = threading.Event()
        ret = []
        method = protocol.Request.Method.Value(method.upper())
        with self.req_id_lock:
            req_id = self.req_id
            self.req_id += 1
        def ack_fn(result):
            ret[0] = int(result)
            done.set()
        def send_fn(tsock):
            self.callbacks[req_id] = callback
            self.ack_callbacks[req_id] = ack_fn
            req = protocol.Request(id=req_id,method=method,path=path,
                                   query=query,session=session,headers=headers)
            tsock.send(req.SerializeToString())
        self.enqueue(send_fn)
        done.wait()
        return ret[0]

    def request_headers_async(self, callback, method, path, query=None,
                              session=None):
        return self.request_async(callback, method, path, query, session, True)

    def request(self, method, path, query=None, session=None, headers=False):
        fulfillment = threading.Event()
        retval = []
        def callback(response):
            retval[0] = response
            fulfillment.set()
        self.request_async(method, callback, path, query, session, headers)
        fulfillment.wait()
        return retval[0]

    def request_headers(self, method, path, query=None, session=None):
        return self.request(method, path, query, session, True)

class Response(namedtuple('Response','result response')):
    """
    A Response from NationStates.net via Trawler
    """
    def read(self):
        return self.response

def default_connection():
    if not default_connection.conn:
        default_connection.conn = \
            Connection('localhost', 5557, default_user_agent())
    return default_connection.conn
default_connection.conn = None

def default_user_agent():
    return "trawler "+version()

from _version import GITHASH
def version():
    return "v0.0.1 (https://github.com/Eluvatar/trawler-client-py/tree/{0})".format(GITHASH)
