# coding=utf-8
import json
import os

import dateutil.parser
import six
import termcolor

from . import dtslogger
from .utils import raise_wrapped, indent


class Storage(object):
    done = False


DEFAULT_DTSERVER = 'https://challenges.duckietown.org/v3'


def get_duckietown_server_url():
    V = 'DTSERVER'

    if V in os.environ:
        use = os.environ[V]
        if not Storage.done:
            if use != DEFAULT_DTSERVER:
                msg = 'Using server %s instead of default %s' % (use, DEFAULT_DTSERVER)
                dtslogger.info(msg)
            Storage.done = True
        return use
    else:
        return DEFAULT_DTSERVER


class RequestException(Exception):
    pass


class ConnectionError(RequestException):
    """ The server could not be reached or completed request or
        provided an invalid or not well-formatted answer. """


class RequestFailed(RequestException):
    """
        The server said the request was invalid.

        Answered  {'ok': False, 'error': msg}
    """


DEFAULT_TIMEOUT = 5


def make_server_request(token, endpoint, data=None, method='GET', timeout=DEFAULT_TIMEOUT,
                        suppress_user_msg=False):
    """
        Raise RequestFailed or ConnectionError.

        Returns the result in 'result'.
    """

    from six.moves import urllib
    # import urllib.request

    server = get_duckietown_server_url()
    url = server + endpoint

    headers = {}
    if token is not None:
        headers['X-Messaging-Token'] = token

    if data is not None:
        data = json.dumps(data)
        if six.PY3:
            data = data.encode('utf-8')
    req = urllib.request.Request(url, headers=headers, data=data)
    req.get_method = lambda: method
    try:
        res = urllib.request.urlopen(req, timeout=timeout)
        data = res.read()
    except urllib.error.HTTPError as e:
        msg = 'Operation failed for %s' % url
        msg += '\n\n' + e.read()
        raise ConnectionError(msg)
    except urllib.error.URLError as e:
        msg = 'Cannot connect to server %s' % url
        raise_wrapped(ConnectionError, e, msg)
        raise

    try:
        result = json.loads(data)
    except ValueError as e:
        msg = 'Cannot read answer from server.'
        msg += '\n\n' + indent(data, '  > ')
        raise_wrapped(ConnectionError, e, msg)
        raise

    if not isinstance(result, dict) or 'ok' not in result:
        msg = 'Server provided invalid JSON response. Expected a dict with "ok" in it.'
        msg += '\n\n' + indent(data, '  > ')
        raise ConnectionError(msg)

    if 'user_msg' in result and not suppress_user_msg:
        user_msg = result['user_msg']
        if user_msg:
            s = []
            lines = user_msg.strip().split('\n')
            prefix = u'message from server: '
            p2 = u': '.rjust(len(prefix))
            print('')
             
            for i, l in enumerate(lines):
                p = prefix if i == 0 else p2
                # l = termcolor.colored(l, 'blue')
                s.append(termcolor.colored(p, attrs=['dark']) + l)
            from dt_shell.cli import dts_print

            dts_print('\n'.join(s))

    if result['ok']:
        if 'result' not in result:
            msg = 'Server provided invalid JSON response. Expected a field "result".'
            msg += '\n\n' + indent(result, '  > ')
            raise ConnectionError(msg)
        return result['result']
    else:
        msg = result.get('msg', 'no error message in %s ' % result)
        msg = 'Failed request for %s:\n%s' % (url, msg)
        raise RequestFailed(msg)


def get_dtserver_user_info(token):
    """ Returns a dictionary with information about the user """
    endpoint = '/info'
    method = 'GET'
    data = None
    return make_server_request(token, endpoint, data=data, method=method)


def dtserver_submit(token, queue, data):
    endpoint = '/submissions'
    method = 'POST'
    data = {'queue': queue, 'parameters': data}
    return make_server_request(token, endpoint, data=data, method=method)


def dtserver_retire(token, submission_id):
    endpoint = '/submissions'
    method = 'DELETE'
    data = {'submission_id': submission_id}
    return make_server_request(token, endpoint, data=data, method=method)


def dtserver_get_user_submissions(token):
    """ Returns a dictionary with information about the user submissions """
    endpoint = '/submissions'
    method = 'GET'
    data = {}
    submissions = make_server_request(token, endpoint, data=data, method=method)

    for v in submissions.values():
        for k in ['date_submitted', 'last_status_change']:
            v[k] = dateutil.parser.parse(v[k])
    return submissions
