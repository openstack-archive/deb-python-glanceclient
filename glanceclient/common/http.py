# Copyright 2012 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import copy
import errno
import hashlib
import httplib
import logging
import posixpath
import socket
import StringIO
import struct
import urlparse

try:
    import json
except ImportError:
    import simplejson as json

# Python 2.5 compat fix
if not hasattr(urlparse, 'parse_qsl'):
    import cgi
    urlparse.parse_qsl = cgi.parse_qsl

import OpenSSL

from glanceclient import exc
from glanceclient.common import utils
from glanceclient.openstack.common import strutils

try:
    from eventlet import patcher
    # Handle case where we are running in a monkey patched environment
    if patcher.is_monkey_patched('socket'):
        from eventlet.green.httplib import HTTPSConnection
        from eventlet.green.OpenSSL.SSL import GreenConnection as Connection
        from eventlet.greenio import GreenSocket
        # TODO(mclaren): A getsockopt workaround: see 'getsockopt' doc string
        GreenSocket.getsockopt = utils.getsockopt
    else:
        raise ImportError
except ImportError:
    from httplib import HTTPSConnection
    from OpenSSL.SSL import Connection as Connection


LOG = logging.getLogger(__name__)
USER_AGENT = 'python-glanceclient'
CHUNKSIZE = 1024 * 64  # 64kB


class HTTPClient(object):

    def __init__(self, endpoint, **kwargs):
        self.endpoint = endpoint
        endpoint_parts = self.parse_endpoint(self.endpoint)
        self.endpoint_scheme = endpoint_parts.scheme
        self.endpoint_hostname = endpoint_parts.hostname
        self.endpoint_port = endpoint_parts.port
        self.endpoint_path = endpoint_parts.path

        self.connection_class = self.get_connection_class(self.endpoint_scheme)
        self.connection_kwargs = self.get_connection_kwargs(
            self.endpoint_scheme, **kwargs)

        self.identity_headers = kwargs.get('identity_headers')
        self.auth_token = kwargs.get('token')
        if self.identity_headers:
            if self.identity_headers.get('X-Auth-Token'):
                self.auth_token = self.identity_headers.get('X-Auth-Token')
                del self.identity_headers['X-Auth-Token']

    @staticmethod
    def parse_endpoint(endpoint):
        return urlparse.urlparse(endpoint)

    @staticmethod
    def get_connection_class(scheme):
        if scheme == 'https':
            return VerifiedHTTPSConnection
        else:
            return httplib.HTTPConnection

    @staticmethod
    def get_connection_kwargs(scheme, **kwargs):
        _kwargs = {'timeout': float(kwargs.get('timeout', 600))}

        if scheme == 'https':
            _kwargs['cacert'] = kwargs.get('cacert', None)
            _kwargs['cert_file'] = kwargs.get('cert_file', None)
            _kwargs['key_file'] = kwargs.get('key_file', None)
            _kwargs['insecure'] = kwargs.get('insecure', False)
            _kwargs['ssl_compression'] = kwargs.get('ssl_compression', True)

        return _kwargs

    def get_connection(self):
        _class = self.connection_class
        try:
            return _class(self.endpoint_hostname, self.endpoint_port,
                          **self.connection_kwargs)
        except httplib.InvalidURL:
            raise exc.InvalidEndpoint()

    def log_curl_request(self, method, url, kwargs):
        curl = ['curl -i -X %s' % method]

        for (key, value) in kwargs['headers'].items():
            header = '-H \'%s: %s\'' % (key, value)
            curl.append(header)

        conn_params_fmt = [
            ('key_file', '--key %s'),
            ('cert_file', '--cert %s'),
            ('cacert', '--cacert %s'),
        ]
        for (key, fmt) in conn_params_fmt:
            value = self.connection_kwargs.get(key)
            if value:
                curl.append(fmt % value)

        if self.connection_kwargs.get('insecure'):
            curl.append('-k')

        if kwargs.get('body') is not None:
            curl.append('-d \'%s\'' % kwargs['body'])

        curl.append('%s%s' % (self.endpoint, url))
        LOG.debug(strutils.safe_encode(' '.join(curl)))

    @staticmethod
    def log_http_response(resp, body=None):
        status = (resp.version / 10.0, resp.status, resp.reason)
        dump = ['\nHTTP/%.1f %s %s' % status]
        dump.extend(['%s: %s' % (k, v) for k, v in resp.getheaders()])
        dump.append('')
        if body:
            dump.extend([body, ''])
        LOG.debug(strutils.safe_encode('\n'.join(dump)))

    @staticmethod
    def encode_headers(headers):
        """Encodes headers.

        Note: This should be used right before
        sending anything out.

        :param headers: Headers to encode
        :returns: Dictionary with encoded headers'
                  names and values
        """
        to_str = strutils.safe_encode
        return dict([(to_str(h), to_str(v)) for h, v in headers.iteritems()])

    def _http_request(self, url, method, **kwargs):
        """Send an http request with the specified characteristics.

        Wrapper around httplib.HTTP(S)Connection.request to handle tasks such
        as setting headers and error handling.
        """
        # Copy the kwargs so we can reuse the original in case of redirects
        kwargs['headers'] = copy.deepcopy(kwargs.get('headers', {}))
        kwargs['headers'].setdefault('User-Agent', USER_AGENT)
        if self.auth_token:
            kwargs['headers'].setdefault('X-Auth-Token', self.auth_token)

        if self.identity_headers:
            for k, v in self.identity_headers.iteritems():
                kwargs['headers'].setdefault(k, v)

        self.log_curl_request(method, url, kwargs)
        conn = self.get_connection()

        # Note(flaper87): Before letting headers / url fly,
        # they should be encoded otherwise httplib will
        # complain. If we decide to rely on python-request
        # this wont be necessary anymore.
        kwargs['headers'] = self.encode_headers(kwargs['headers'])

        try:
            if self.endpoint_path:
                url = '%s/%s' % (self.endpoint_path, url)
            conn_url = posixpath.normpath(url)
            # Note(flaper87): Ditto, headers / url
            # encoding to make httplib happy.
            conn_url = strutils.safe_encode(conn_url)
            if kwargs['headers'].get('Transfer-Encoding') == 'chunked':
                conn.putrequest(method, conn_url)
                for header, value in kwargs['headers'].items():
                    conn.putheader(header, value)
                conn.endheaders()
                chunk = kwargs['body'].read(CHUNKSIZE)
                # Chunk it, baby...
                while chunk:
                    conn.send('%x\r\n%s\r\n' % (len(chunk), chunk))
                    chunk = kwargs['body'].read(CHUNKSIZE)
                conn.send('0\r\n\r\n')
            else:
                conn.request(method, conn_url, **kwargs)
            resp = conn.getresponse()
        except socket.gaierror as e:
            message = "Error finding address for %s: %s" % (
                self.endpoint_hostname, e)
            raise exc.InvalidEndpoint(message=message)
        except (socket.error, socket.timeout) as e:
            endpoint = self.endpoint
            message = "Error communicating with %(endpoint)s %(e)s" % locals()
            raise exc.CommunicationError(message=message)

        body_iter = ResponseBodyIterator(resp)

        # Read body into string if it isn't obviously image data
        if resp.getheader('content-type', None) != 'application/octet-stream':
            body_str = ''.join([chunk for chunk in body_iter])
            self.log_http_response(resp, body_str)
            body_iter = StringIO.StringIO(body_str)
        else:
            self.log_http_response(resp)

        if 400 <= resp.status < 600:
            LOG.error("Request returned failure status.")
            raise exc.from_response(resp, body_str)
        elif resp.status in (301, 302, 305):
            # Redirected. Reissue the request to the new location.
            return self._http_request(resp['location'], method, **kwargs)
        elif resp.status == 300:
            raise exc.from_response(resp)

        return resp, body_iter

    def json_request(self, method, url, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers'].setdefault('Content-Type', 'application/json')

        if 'body' in kwargs:
            kwargs['body'] = json.dumps(kwargs['body'])

        resp, body_iter = self._http_request(url, method, **kwargs)

        if 'application/json' in resp.getheader('content-type', None):
            body = ''.join([chunk for chunk in body_iter])
            try:
                body = json.loads(body)
            except ValueError:
                LOG.error('Could not decode response body as JSON')
        else:
            body = None

        return resp, body

    def raw_request(self, method, url, **kwargs):
        kwargs.setdefault('headers', {})
        kwargs['headers'].setdefault('Content-Type',
                                     'application/octet-stream')
        if 'body' in kwargs:
            if (hasattr(kwargs['body'], 'read')
                    and method.lower() in ('post', 'put')):
                # We use 'Transfer-Encoding: chunked' because
                # body size may not always be known in advance.
                kwargs['headers']['Transfer-Encoding'] = 'chunked'
        return self._http_request(url, method, **kwargs)


class OpenSSLConnectionDelegator(object):
    """
    An OpenSSL.SSL.Connection delegator.

    Supplies an additional 'makefile' method which httplib requires
    and is not present in OpenSSL.SSL.Connection.

    Note: Since it is not possible to inherit from OpenSSL.SSL.Connection
    a delegator must be used.
    """
    def __init__(self, *args, **kwargs):
        self.connection = Connection(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def makefile(self, *args, **kwargs):
        # Making sure socket is closed when this file is closed
        # since we now avoid closing socket on connection close
        # see new close method under VerifiedHTTPSConnection
        kwargs['close'] = True

        return socket._fileobject(self.connection, *args, **kwargs)


class VerifiedHTTPSConnection(HTTPSConnection):
    """
    Extended HTTPSConnection which uses the OpenSSL library
    for enhanced SSL support.
    Note: Much of this functionality can eventually be replaced
          with native Python 3.3 code.
    """
    def __init__(self, host, port=None, key_file=None, cert_file=None,
                 cacert=None, timeout=None, insecure=False,
                 ssl_compression=True):
        HTTPSConnection.__init__(self, host, port,
                                 key_file=key_file,
                                 cert_file=cert_file)
        self.key_file = key_file
        self.cert_file = cert_file
        self.timeout = timeout
        self.insecure = insecure
        self.ssl_compression = ssl_compression
        self.cacert = cacert
        self.setcontext()

    @staticmethod
    def host_matches_cert(host, x509):
        """
        Verify that the the x509 certificate we have received
        from 'host' correctly identifies the server we are
        connecting to, ie that the certificate's Common Name
        or a Subject Alternative Name matches 'host'.
        """
        # First see if we can match the CN
        if x509.get_subject().commonName == host:
            return True

        # Also try Subject Alternative Names for a match
        san_list = None
        for i in xrange(x509.get_extension_count()):
            ext = x509.get_extension(i)
            if ext.get_short_name() == 'subjectAltName':
                san_list = str(ext)
                for san in ''.join(san_list.split()).split(','):
                    if san == "DNS:%s" % host:
                        return True

        # Server certificate does not match host
        msg = ('Host "%s" does not match x509 certificate contents: '
               'CommonName "%s"' % (host, x509.get_subject().commonName))
        if san_list is not None:
            msg = msg + ', subjectAltName "%s"' % san_list
        raise exc.SSLCertificateError(msg)

    def verify_callback(self, connection, x509, errnum,
                        depth, preverify_ok):
        # NOTE(leaman): preverify_ok may be a non-boolean type
        preverify_ok = bool(preverify_ok)
        if x509.has_expired():
            msg = "SSL Certificate expired on '%s'" % x509.get_notAfter()
            raise exc.SSLCertificateError(msg)

        if depth == 0 and preverify_ok:
            # We verify that the host matches against the last
            # certificate in the chain
            return self.host_matches_cert(self.host, x509)
        else:
            # Pass through OpenSSL's default result
            return preverify_ok

    def setcontext(self):
        """
        Set up the OpenSSL context.
        """
        self.context = OpenSSL.SSL.Context(OpenSSL.SSL.SSLv23_METHOD)

        if self.ssl_compression is False:
            self.context.set_options(0x20000)  # SSL_OP_NO_COMPRESSION

        if self.insecure is not True:
            self.context.set_verify(OpenSSL.SSL.VERIFY_PEER,
                                    self.verify_callback)
        else:
            self.context.set_verify(OpenSSL.SSL.VERIFY_NONE,
                                    lambda *args: True)

        if self.cert_file:
            try:
                self.context.use_certificate_file(self.cert_file)
            except Exception as e:
                msg = 'Unable to load cert from "%s" %s' % (self.cert_file, e)
                raise exc.SSLConfigurationError(msg)
            if self.key_file is None:
                # We support having key and cert in same file
                try:
                    self.context.use_privatekey_file(self.cert_file)
                except Exception as e:
                    msg = ('No key file specified and unable to load key '
                           'from "%s" %s' % (self.cert_file, e))
                    raise exc.SSLConfigurationError(msg)

        if self.key_file:
            try:
                self.context.use_privatekey_file(self.key_file)
            except Exception as e:
                msg = 'Unable to load key from "%s" %s' % (self.key_file, e)
                raise exc.SSLConfigurationError(msg)

        if self.cacert:
            try:
                self.context.load_verify_locations(self.cacert)
            except Exception as e:
                msg = 'Unable to load CA from "%s"' % (self.cacert, e)
                raise exc.SSLConfigurationError(msg)
        else:
            self.context.set_default_verify_paths()

    def connect(self):
        """
        Connect to an SSL port using the OpenSSL library and apply
        per-connection parameters.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if self.timeout is not None:
            # '0' microseconds
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO,
                            struct.pack('fL', self.timeout, 0))
        self.sock = OpenSSLConnectionDelegator(self.context, sock)
        self.sock.connect((self.host, self.port))

    def close(self):
        if self.sock:
            # Removing reference to socket but don't close it yet.
            # Response close will close both socket and associated
            # file. Closing socket too soon will cause response
            # reads to fail with socket IO error 'Bad file descriptor'.
            self.sock = None

        # Calling close on HTTPConnection to continue doing that cleanup.
        HTTPSConnection.close(self)


class ResponseBodyIterator(object):
    """
    A class that acts as an iterator over an HTTP response.

    This class will also check response body integrity when iterating over
    the instance and if a checksum was supplied using `set_checksum` method,
    else by default the class will not do any integrity check.
    """

    def __init__(self, resp):
        self._resp = resp
        self._checksum = None
        self._size = int(resp.getheader('content-length', 0))
        self._end_reached = False

    def set_checksum(self, checksum):
        """
        Set checksum to check against when iterating over this instance.

        :raise: AttributeError if iterator is already consumed.
        """
        if self._end_reached:
            raise AttributeError("Can't set checksum for an already consumed"
                                 " iterator")
        self._checksum = checksum

    def __len__(self):
        return int(self._size)

    def __iter__(self):
        md5sum = hashlib.md5()
        while True:
            try:
                chunk = self.next()
            except StopIteration:
                self._end_reached = True
                # NOTE(mouad): Check image integrity when the end of response
                # body is reached.
                md5sum = md5sum.hexdigest()
                if self._checksum is not None and md5sum != self._checksum:
                    raise IOError(errno.EPIPE,
                                  'Corrupted image. Checksum was %s '
                                  'expected %s' % (md5sum, self._checksum))
                raise
            else:
                yield chunk
                md5sum.update(chunk)

    def next(self):
        chunk = self._resp.read(CHUNKSIZE)
        if chunk:
            return chunk
        else:
            raise StopIteration()
