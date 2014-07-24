#    Copyright 2013-2014 Eluvatar
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
from StringIO import StringIO

def is_open(tsock):
    return not tsock.closed

def kwargs_filter(*args, **kwargs):
    kwargs2 = dict((k, v) for k, v in kwargs.iteritems() if v)
    return kwargs2

class Request(namedtuple('Request','id request ack_callback acked callback')):
    """
    A request of the library to make an HTTP request of ns via trawler.
    """

class Connection(object):
    """
    A connection to a Trawler daemon. Has a worker thread which owns
    all interaction with the zmq socket pointed at said daemon.
    """
    def __init__(self, host, port, user_agent_str):
        self.url = "tcp://{0}:{1}".format(host, port)
        self.user_agent = user_agent_str
        self.req_id = 1
        self.req_id_lock = threading.Lock()
        self.reqs = dict()
        self.opening = threading.Event()
        self.opened = threading.Event()
        self.queue = Queue()
        tname = "Connection {0} worker".format(id(self))
        thread = threading.Thread(name=tname, target=self.worker)
        thread.daemon = True
        thread.start()

    def worker(self):
        qsock = zmq.Context.instance().socket(zmq.PULL)
        qsock.bind("inproc://request_queue-"+str(id(self)))
        poller = zmq.Poller()
        tsock = zmq.Context.instance().socket(zmq.DEALER)
        poller.register(tsock, zmq.POLLIN)
        poller.register(qsock, zmq.POLLIN)
        while(True):
            self.opening.wait()
            self.open(tsock)
            self.login(tsock)
            self.opened.set()
            while is_open(tsock):
                socks = dict(poller.poll())
                if qsock in socks and socks[qsock] == zmq.POLLIN:
                    qsock.recv()
                    while not self.queue.empty():
                        todo = self.queue.get_nowait()
                        todo(tsock)
                        self.queue.task_done()
                if tsock in socks and socks[tsock] == zmq.POLLIN:
                    self.receive(tsock)
            self.opening.clear()
            self.opened.clear()

    def login(self, tsock):
        login_message = protocol.Login(user_agent=self.user_agent)
        tsock.send(login_message.SerializeToString())

    assert(protocol.Reply.Response == 0)
    assert(protocol.Reply.Ack == 1) 
    assert(protocol.Reply.Nack == 2)
    assert(protocol.Reply.Logout == 3)
    def receive(self, tsock):
        reply = protocol.Reply()
        reply.ParseFromString(tsock.recv_multipart()[-1])
        # TODO print reply in debug mode of some kind
        # print reply
        if( reply.reply_type < 0 or reply.reply_type > 2 ):
            if( reply.reply_type == protocol.Reply.Logout ):
                self.logout(reply, tsock)
            else:
                self.invalid(reply, tsock)
            return
        [ self.response, self.ack, self.nack ][reply.reply_type](reply)

    def ack(self, reply):
        req = self.reqs[reply.req_id]
        req.acked = True
        req.ack_callback(reply.result)

    def nack(self, reply):
        self.ack(self, reply)
        self.reqs[reply.req_id].callback(Response(result=reply.result))
        del self.reqs[reply.req_id]

    def response(self, reply):
        req_id = reply.req_id
        if reply.headers:
            response = reply.headers + reply.response
        else:
            response = reply.response
        req = self.reqs[req_id]
        req.callback(Response(result=reply.result, response=response))
        del self.reqs[reply.req_id]

    def logout(self, reply, tsock):
        for req_id in self.reqs.keys():
            req = self.reqs[req_id]
            if not self.acked:
                 req.ack_callback[req_id](reply.result)
            req.callback(Response(result=reply.result, response=''))
            del self.reqs[req_id]
        tsock.close()

    def invalid(self, reply, tsock):
        for req_id in self.reqs.keys():
            req = self.reqs[req_id]
            if not self.acked:
                 req.ack_callback[req_id](530)
            req.callback(Response(530, response=''))
            del self.reqs[req_id]
        tsock.close()

    def require_open(dep_fn):
        def impl_fn(*args, **kwargs):
            self=args[0]
            self.opening.set()
            self.opened.wait()
            return dep_fn(*args, **kwargs)
        return impl_fn

    def open(self, tsock):
        tsock.connect(self.url)

    def enqueue(self, qfn):
        done = threading.Event()
        ret = [None]
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
        ret = [0]
        method = protocol.Request.Method.Value(method.upper())
        with self.req_id_lock:
            req_id = self.req_id
            self.req_id += 1
        def ack_fn(result):
            ret[0] = int(result)
            done.set()
        def send_fn(tsock):
            kwf = kwargs_filter
            req = protocol.Request(**kwf(id=req_id,method=method,path=path,
                                         query=query,session=session,headers=headers))
            self.reqs[req_id] = Request(req_id, req, ack_fn, False, callback)
            tsock.send(req.SerializeToString())
        self.enqueue(send_fn)
        done.wait()
        return ret[0]

    def request_headers_async(self, callback, method, path, query=None,
                              session=None):
        return self.request_async(callback, method, path, query, session, True)

    def request(self, method, path, query=None, session=None, headers=False):
        fulfillment = threading.Event()
        retval = [0]
        def callback(response):
            retval[0] = response
            fulfillment.set()
        self.request_async(callback, method, path, query, session, headers)
        fulfillment.wait()
        return retval[0]

    def request_headers(self, method, path, query=None, session=None):
        return self.request(method, path, query, session, True)

class Response(namedtuple('Response','result response')):
    """
    A Response from NationStates.net via Trawler
    """
    def __new__(self, result, response):
        self.strio = StringIO(response)
        return tuple.__new__(Response, (result, response)) 

    def read(self,size=-1):
        return self.strio.read(size)


def version():
    return "v0.1.0"
