#   Copyright 2013-2014 Eluvatar
#
#   This file is part of Trawler.
#
#   Trawler is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   Trawler is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with Trawler.  If not, see <http://www.gnu.org/licenses/>.

"""
  This module defines a python interface toward being a Trawler client.
  Trawler is a system for sharing rate-limited access to
  NationStates.net among multiple (prioritized) programs with minimal
  sharing of state.

  This interface provides request methods which return Response objects
  as well as (TODO) a common result code type. The result code is styled
  as an exit code: T_OK is zero.
"""

from . import _trawler

def _instance():
    return default_connection()

def request(*args, **kwargs):
    """
    Issues a request given keyword arguments for method (an RFC 2616
    method string), path (the part after the domain and before any
    query string), query (the query string, when part of a GET request,
    is also known as a search string), session (the cookie value to
    send), and header (a flag for whether to include the headers in the
    returned result -- the default is to only return the body).

    The method and path arguments are required. The rest are not.

    This method blocks. (It will not return until the response is
    available, and it will return the response.)
    """
    return _instance().request(*args, **kwargs)
def request_headers(*args, **kwargs):
    """
    Issues a request (for headers and body) given keyword arguments for
    method (an RFC 2616 method string), path (the part after the domain
    and before any query string), query (the query string, when part of
    a GET request, is also known as a search string), and session (the
    cookie value to send).

    The method and path arguments are required. The rest are not.

    This method blocks. (It will not return until the response is
    available, and it will return the response.)
    """
    return _instance().request_headers(*args, **kwargs)
def request_async(*args, **kwargs):
    """
    Issues a request given keyword arguments for callback (a function
    which takes a single Response object argument), method (an RFC 2616
    method string), path (the part after the domain and before any
    query string), query (the query string, when part of a GET request,
    is also known as a search string), session (the cookie value to
    send), and header (a flag for whether to include the headers in the
    returned result -- the default is to only return the body).

    The method and path arguments are required. The rest are not.

    This method blocks. (It will not return until the request is acknowledged
    by the trawler daemon. The callback will be invoked asynchronously.)
    """
    return _instance().request_async(*args, **kwargs)
def request_headers_async(*args, **kwargs):
    """
    Issues a request given keyword arguments for callback (a function 
    which takes a single Response object argument), method (an RFC 2616
    method string), path (the part after the domain and before any query
    string), query (the query string, when part of a GET request, is also
    known as a search string), session (the cookie value to send), making
    sure to return the headers as well.

    The method and path arguments are required. The rest are not.

    This method blocks. (It will not return until the request is acknowledged
    by the trawler daemon. The callback will be invoked asynchronously.)
    """
    return _instance().request_headers_async(*args, **kwargs)

def connection(user_agent):
    """Return a connection object given a particular user_agent to the default
    localhost:5557 trawler daemon"""
    return _trawler.Connection('localhost', 5557, user_agent)

def version():
    """Return the client library version string"""
    return _trawler.version()

def default_connection():
    """Return a connection object given the default user_agent to the default
    localhost:5557 trawler daemon.

    Note: the default user_agent must be set as a module-level attribute."""
    if not default_connection.conn:
        default_connection.conn = \
            connection(default_user_agent())
    return default_connection.conn
default_connection.conn = None

user_agent = None
def default_user_agent():
    if user_agent:
        return user_agent
    else:
        raise Exception("User Agent required")
