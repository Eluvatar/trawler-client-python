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

import zmq
import threading
from Queue import Queue
from collections import namedtuple

class Connection(object):
    """
    A connection to a Trawler daemon. Has a worker thread which owns
    all interaction with the zmq socket pointed at said daemon.
    """
    def __init__(self, host, port, user_agent_str):
        self.sock = zmq.Context.instance().socket(zmq.REQ)
        self.url = "tcp://{0}:{1}".format(host, port)
        self.user_agent = user_agent_str
        self.opened = False
        self.req_id = 0
        self.req_id_lock = threading.Lock()
        self.callbacks = dict()
        self.opening = threading.Event()
        self.queue = Queue()
        self.queue_cb = dict()
        tname = "Connection {0} worker".format(id(self))
        thread = threading.Thread(name=tname, target=self.worker)
        thread.daemon = True
        thread.start()

    def worker(self):
        qsock = zmq.Context.instance().socket(zmq.PULL)
        qsock.bind("inproc://request_queue-"+str(id(self)))
        poller = zmq.Poller()
        poller.register(self.sock, zmq.POLLIN)
        poller.register(qsock, zmq.POLLIN)
        while(True):
            self.opening.wait()
            self.open()
            while self.is_open():
                socks = dict(poller.poll())
                if qsock in socks and socks[qsock] == zmq.POLLIN:
                    qsock.recv()
                    while not self.queue.empty():
                        (todo, args, kwargs) = self.queue.get_nowait()
                        todo(*args, **kwargs)
                        self.queue.task_done()
                if self.sock in socks and socks[self.sock] == zmq.POLLIN:
                    self.receive()
            self.opening.clear()

    def receive(self):
        mtype = self.sock.recv()
        {
        'ack' : self.recv_ack,
        'nack' : self.recv_nack,
        'response' : self.recv_response,
        }.get(mtype,self.recv_invalid)()

    def recv_ack(self):
        (req_id, result) = self.sock.recv_multipart()
        (done, out) = self.queue_cb[int(req_id)]
        del self.queue_cb[req_id]
        out[0] = int(result)
        done.set()

    def recv_nack(self):
        (req_id_s, result) = self.sock.recv_multipart()
        req_id = int(req_id_s)
        (done, out) = self.queue_cb[req_id]
        del self.queue_cb[req_id]
        out[0] = int(result)
        self.callbacks[req_id](Response(result=result))
        del self.callbacks[req_id]
        done.set()

    def recv_response(self):
        (req_id_s, result, response) = self.sock.recv_multipart()
        req_id = int(req_id_s)
        self.callbacks[req_id](Response(result=int(result), response=response))
        del self.callbacks[req_id]

    def recv_invalid(self):
        #TODO handle failure -- perhaps call all callbacks with an
        # invalid object and raise exception, killing worker thread?
        pass

    def require_open(self, dep_fn):
        def impl_fn(*args, **kwargs):
            if not self.is_open():
                self.opening.set()
            dep_fn(*args, **kwargs)
        return impl_fn

    def queued(self, dep_fn):
        def impl_fn(*args, **kwargs):
            with self.req_id_lock:
                req_id = self.req_id
                self.req_id += 1
            kwargs['req_id'] = req_id
            done = threading.Event()
            ret = [] # TODO result enum
            self.queue_cb[self.req_id] = (done, ret,)
            self.queue.put((dep_fn, args, kwargs,))
            qsock = zmq.Context.instance().socket(zmq.PUSH)
            qsock.connect("inproc://request_queue-"+str(id(self)))
            qsock.send("")
            done.wait()
            return ret[0]
        return impl_fn

    def open(self):
        self.sock.connect(self.url)
        self.opened = True
        self.opening.set()

    def is_open(self):
        return self.opened and not self.sock.closed

    def __nonzero__(self):
        return self.is_open()

    @require_open
    @queued
    def request_async(self, req_id, callback, method, path, query=None,
                      session=None, headers=False):
        self.callbacks[req_id] = callback
        tup = (str(req_id), method, path, query, session, headers,)
        self.sock.send_multipart(tup)

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
    def read(self):
        return self.response

default_connection.conn = None
def default_connection():
    if not default_connection.conn:
        default_connection.conn = \
            Connection('localhost', 5557, default_user_agent())
    return default_connection.conn

def default_user_agent():
    return "trawler "+version()

def version():
    return "v0.0.1 (NIL)"
