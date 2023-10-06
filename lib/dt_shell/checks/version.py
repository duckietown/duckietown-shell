# -*- coding: utf-8 -*-
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple

import requests
import termcolor
import yaml
from requests import Response, HTTPError

from .. import __version__
from ..constants import DTShellConstants
from ..exceptions import CouldNotGetVersion, NoCacheAvailable, URLException


def get_url(url, timeout=3) -> str:
    try:
        response: Response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return response.text
    except HTTPError as e:
        raise URLException(str(e))
    except ConnectionError as e:
        raise URLException(str(e))


def get_last_version_fresh() -> str:
    url = "https://pypi.org/pypi/duckietown-shell/json"

    try:
        try:
            data = get_url(url)
        except URLException as e:
            raise CouldNotGetVersion(str(e))
        try:
            info = json.loads(data)
        except BaseException as e:
            msg = "Could not read json %r" % data
            raise CouldNotGetVersion(msg) from e

        last_version = info["info"]["version"]
        return last_version
    except CouldNotGetVersion:
        raise
    except BaseException as e:
        raise CouldNotGetVersion() from e


def get_cache_filename() -> str:
    d0 = os.path.expanduser(DTShellConstants.ROOT)
    return os.path.join(d0, "pypi-cache.yaml")


def read_cache() -> Tuple[str, datetime]:
    try:
        fn = get_cache_filename()
        if os.path.exists(fn):
            data = open(fn).read()
            interpreted = yaml.load(data, Loader=yaml.Loader)
            version = interpreted["version"]
            dt = interpreted["timestamp"]
            return version, dt
        else:
            msg = "File %s does not exist." % fn
            raise NoCacheAvailable(msg)
    except Exception as e:
        msg = "Could not read cache: %s" % e
        raise NoCacheAvailable(msg)


def write_cache(version: str, dt: datetime) -> None:
    fn = get_cache_filename()
    d0 = os.path.dirname(fn)
    if not os.path.exists(d0):
        os.makedirs(d0)

    with open(fn, "w") as f:
        contents = dict(version=version, timestamp=dt)
        y = yaml.dump(contents)
        f.write(y)


def get_last_version() -> Optional[str]:
    now = datetime.now()
    update = False

    version = None
    try:
        version, timestamp = read_cache()
    except NoCacheAvailable:
        timestamp = now
        update = True

    if not update:
        delta = now - timestamp
        if delta > timedelta(minutes=10):
            # logger.debug('Version cache is outdated (%s).' % delta)
            update = True

    if update:
        # logger.debug('Getting last version from PyPI.')
        try:
            version = get_last_version_fresh()
            write_cache(version, now)
            return version
        except CouldNotGetVersion:
            return None

    # XXX: this might not be set
    return version


def is_older(a: str, b: str) -> bool:
    na = tuple(map(int, a.split(".")))
    nb = tuple(map(int, b.split(".")))

    return na < nb


def check_for_updates() -> None:
    latest_version = get_last_version()
    # print('last version: %r' % latest_version)
    # print('installed: %r' % __version__)

    # TODO: this should take into account the profile we are using and the max major version declared in them

    if latest_version and is_older(__version__, latest_version):
        msg = """

There is an updated duckietown-shell available.

  You have: {current}

  Available: {available} 
 
WARNING: We strongly recommend updating to the latest version. ONLY THE LATEST VERSION IS SUPPORTED!
         If you experience issues, please make sure you're using the latest version before posting 
         questions or issues. 

You can update the shell using `pip`. Run the following command:
        pip3 install --no-cache-dir --user -U duckietown-shell

        """.format(
            current=__version__, available=latest_version
        )
        print(termcolor.colored(msg, "yellow"))
