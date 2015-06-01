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
import mimetools

def is_open(tsock):
    return not tsock.closed

def kwargs_filter(*args, **kwargs):
    kwargs2 = dict((k, v) for k, v in kwargs.iteritems() if v)
    return kwargs2

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
        self.responses = dict()
        self.callbacks = dict()
        self.opening = threading.Event()
        self.opened = threading.Event()
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
        self.ack_callbacks[reply.req_id](reply.result)
        del self.ack_callbacks[reply.req_id]

    def nack(self, reply):
        self.ack(reply)
        self.callbacks[reply.req_id](Response(result=reply.result))
        del self.callbacks[reply.req_id]

    def response(self, reply):
        req_id = reply.req_id
        if req_id in self.callbacks:
            response = Response(result=reply.result, headers=reply.headers,
                                response=reply.response)
            self.responses[req_id] = response
            self.callbacks[req_id](response)
            del self.callbacks[req_id]
        elif reply.headers:
            response = self.responses[req_id]
            response.add_headers(reply.headers)
        elif reply.response:
            response = self.responses[req_id]
            response.add_body(reply.response)
        if not reply.continued:
            self.responses[req_id]._complete()
            del self.responses[req_id]

    def logout(self, reply, tsock):
        for req_id in self.ack_callbacks.keys():
            self.ack_callbacks[req_id](reply.result)
            del self.ack_callbacks[req_id]
        for req_id in self.callbacks.keys():
            self.callbacks[req_id](Response(result=reply.result))
            del self.callbacks[req_id]
        tsock.close()

    def invalid(self, reply, tsock):
        for req_id in self.ack_callbacks.keys():
            self.ack_callbacks[req_id](500)
            del self.ack_callbacks[req_id]
        for req_id in self.callbacks.keys():
            self.callbacks[req_id](Response(result=500))
            del self.callbacks[req_id]
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
            self.callbacks[req_id] = callback
            self.ack_callbacks[req_id] = ack_fn
            kwf = kwargs_filter
            req = protocol.Request(**kwf(id=req_id,method=method,path=path,
                                         query=query,session=session,headers=headers))
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

class TStringIO(StringIO):
    def __init__(self, *args, **kwargs):
        StringIO.__init__(self, *args, **kwargs)
        self.lock = threading.Lock()
        self.done = threading.Event()
    
    def append(self,append_str):
            with self.lock:
                pos = self.tell()
                self.seek(0,2)
                self.write(append_str)
                self.seek(pos)
    
    def read(self,size=-1):
        with self.lock:
            pos = self.tell()
            s = StringIO.read(self,size)
        if not self.done.isSet() and ( size == -1 or len(s) < size):
            self.done.wait()
            with self.lock:
                self.seek(pos)
                return StringIO.read(self,size)
        return s

class Response():
    """
    A Response from NationStates.net via Trawler
    """
    def __init__(self, result, headers=None, response=''):
        self.result = result
        if headers:
            self.header_buf = TStringIO('\r\n'.join(headers.split('\r\n')[1:]))
        else:
            self.header_buf = None
        self.headers = None
        self.body = TStringIO(response or '')
    
    def add_headers(self,headers):
        self.header_buf.append(headers)
    
    def add_body(self,body):
        if self.header_buf:
            self.header_buf.done.set()
        self.body.append(body)
    
    def seek(self,pos,from_what=0):
        self.body.seek(pos,from_what)

    def read(self,size=-1):
        return self.body.read(size)
     
    def info(self):
        if not self.headers and self.header_buf:
            self.header_buf.seek(0)
            self.headers = mimetools.Message( self.header_buf )
        return self.headers

    def getcode(self):
        return self.result
    
    def _complete(self):
        self.body.done.set()

def version():
    return "v0.1.0"
