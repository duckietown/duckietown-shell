# -*- coding: utf-8 -*-
import logging

logging.basicConfig()

dtslogger = logging.getLogger("dts")
dtslogger.setLevel(logging.INFO)

__version__ = "5.0.4"

dtslogger.info("duckietown-shell %s" % __version__)

import sys

if sys.version_info < (3, 6):
    msg = "! duckietown-shell works with Python 3.6 and later !.\nDetected %s." % str(
        sys.version
    )
    logging.error(msg)
    sys.exit(2)

from .exceptions import ConfigInvalid, ConfigNotPresent
from .utils import format_exception

import locale

dtslogger.debug(
    f"encoding: stdout {sys.stdout.encoding} stderr {sys.stderr.encoding} "
    f"locale {locale.getpreferredencoding()}."
)

from .cli import DTShell
from .logging import dts_print

from .dt_command_abs import DTCommandAbs
from .dt_command_placeholder import DTCommandPlaceholder
from .main import cli_main
from .exceptions import *

from .main import OtherVersions
