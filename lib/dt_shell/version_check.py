# -*- coding: utf-8 -*-
from __future__ import print_function

import datetime
import json
import os
import urllib2

import ruamel
import ruamel.yaml as yaml
import termcolor
from system_cmd import system_cmd_result
from whichcraft import which

from . import __version__, dtslogger
from .constants import DTShellConstants


class CouldNotGetVersion(Exception):
    pass


def get_last_version_fresh():
    url = 'https://pypi.org/pypi/duckietown-shell/json'

    try:
        req = urllib2.Request(url)
        try:
            res = urllib2.urlopen(req, timeout=2)
            if res.getcode() != 200: return None
            data = res.read()
        except urllib2.URLError as e:
            # msg = 'Cannot connect to server %s: %s' % (url, (e))
            # raise Exception(msg)
            if which('curl') is not None:
                res = system_cmd_result('.', ['curl', url, '-m', '2'])
                if res.ret != 0: return None
                data = res.stdout
            else:
                raise CouldNotGetVersion()

        info = json.loads(data)
        last_version = info['info']['version']
        return last_version
    except Exception as e:
        raise CouldNotGetVersion(str(e))

def get_cache_filename():
    d0 = os.path.expanduser(DTShellConstants.ROOT)
    return os.path.join(d0, 'pypi-cache.yaml')


class NoCacheAvailable(Exception):
    pass


def read_cache():
    try:
        fn = get_cache_filename()
        if os.path.exists(fn):
            data = open(fn).read()
            interpreted = yaml.load(data, Loader=ruamel.yaml.Loader)
            version = interpreted['version']
            dt = interpreted['timestamp']
            return version, dt
        else:
            msg = 'File %s does not exist.' % fn
            raise NoCacheAvailable(msg)
    except Exception as e:
        msg = 'Could not read cache: %s' % e
        raise NoCacheAvailable(msg)


def write_cache(version, dt):
    fn = get_cache_filename()
    d0 = os.path.dirname(fn)
    if not os.path.exists(d0):
        os.makedirs(d0)

    with open(fn, 'w') as f:
        contents = dict(version=version, timestamp=dt)
        y = yaml.dump(contents)
        f.write(y)


def get_last_version():
    now = datetime.datetime.now()
    update = False
    try:
        version, timestamp = read_cache()
    except NoCacheAvailable:
        timestamp = now
        update = True

    if not update:
        delta = now - timestamp
        if delta > datetime.timedelta(minutes=10):
            dtslogger.debug('Version cache is outdated (%s).' % delta)
            update = True

    if update:
        dtslogger.debug('Getting last version from PyPI.')
        version = get_last_version_fresh()
        if version:
            write_cache(version, now)

    return version


def check_if_outdated():
    latest_version = get_last_version()
    # print('last version: %r' % latest_version)
    # print('installed: %r' % __version__)
    if latest_version and __version__ != latest_version:
        msg = 'There is an updated duckietown-shell available, version %s (you have %s).' % (
            latest_version, __version__)
        msg += '\n\nPlease run:\n\npip install --user -U --no-cache-dir duckietown-shell==%s' % (latest_version)
        msg += '\n\n'
        print(termcolor.colored(msg, 'yellow'))
        return True
    return False
