# -*- coding: utf-8 -*-
from __future__ import print_function

import datetime
import json
import os
import subprocess
import time
from six.moves import urllib

import termcolor
import yaml
from whichcraft import which

from . import __version__, dtslogger
from .constants import DTShellConstants


class CouldNotGetVersion(Exception):
    pass


def get_last_version_fresh():
    url = 'https://pypi.org/pypi/duckietown-shell/json'

    try:
        req = urllib.Request(url)
        try:
            res = urllib.urlopen(req, timeout=2)
            if res.getcode() != 200:
                return None
            data = res.read()
        except urllib.URLError as e:
            # print('falling back to curl')

            if which('curl') is not None:
                cmd = ['curl', url, '-m', '2']
                try:
                    data = subprocess.check_output(cmd, stderr=subprocess.PIPE)
                except subprocess.CalledProcessError as e:
                    msg = 'Could not call %s: %s' % (cmd, e)
                    raise CouldNotGetVersion(msg)
            else:
                msg = 'curl not available'
                raise CouldNotGetVersion(msg)

        try:
            info = json.loads(data)
        except BaseException as e:
            msg = 'Could not read json %r' % data
            raise CouldNotGetVersion(msg)

        last_version = info['info']['version']
        return last_version
    except CouldNotGetVersion:
        raise
    except BaseException as e:
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
            # interpreted = yaml.load(data, Loader=ruamel.yaml.Loader)
            interpreted = yaml.load(data)
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

    version = None
    try:
        version, timestamp = read_cache()
    except NoCacheAvailable:
        timestamp = now
        update = True

    if not update:
        delta = now - timestamp
        if delta > datetime.timedelta(minutes=10):
            # dtslogger.debug('Version cache is outdated (%s).' % delta)
            update = True

    if update:
        # dtslogger.debug('Getting last version from PyPI.')
        try:
            version = get_last_version_fresh()
            write_cache(version, now)
            return version
        except CouldNotGetVersion:
            return None

    # XXX: this might not be set
    return version


def check_if_outdated():
    latest_version = get_last_version()
    # print('last version: %r' % latest_version)
    # print('installed: %r' % __version__)
    if latest_version and __version__ != latest_version:
        msg = '''

There is an updated duckietown-shell available.

  You have: {current}

 available: {available} 

You should update the shell using `pip`.        
        
        '''.format(current=__version__, available=latest_version)
        print(termcolor.colored(msg, 'yellow'))
        wait = 3
        time.sleep(1)
        print('Waiting %d seconds to give you time to read the message.' % wait)
        time.sleep(wait)
        return True
    return False
