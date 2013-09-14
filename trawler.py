#   Copyright 2013 Eluvatar
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

import _trawler

def _instance():
    return _trawler.default_connection()

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

    This method blocks. (It will not return until the response is
    available, and it will return the response.)
    """
    return _instance().request_async(*args, **kwargs)
def request_headers_async(*args, **kwargs):
    return _instance().request_headers_async(*args, **kwargs)
def connection(*args, **kwargs):
    return _trawler.Connection(*args, **kwargs)
def version():
    return _trawler.version()
