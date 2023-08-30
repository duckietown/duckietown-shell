# -*- coding: utf-8 -*-
import logging
from typing import Optional
import pathlib

# ===> COMPATIBILITY
# these are only for older versions of the commands
COMPATIBILITY_DIR = str(pathlib.Path(__file__).parent.joinpath("compatibility").resolve())
__path__ += [COMPATIBILITY_DIR]

from .compatibility import duckietown_tokens
# <=== COMPATIBILITY


logging.basicConfig()

dtslogger = logging.getLogger("dts")
dtslogger.setLevel(logging.INFO)

__version__ = "5.5.10"


dtslogger.debug(f"duckietown-shell {__version__}")

import sys

if sys.version_info < (3, 6):
    msg = f"! duckietown-shell works with Python 3.6 and later !.\nDetected {sys.version}."
    logging.error(msg)
    sys.exit(2)

# This was useful in the days of Python 2. Removing because it breaks when the shell is called
# using pipes (e.g. unit tests).
#
# import locale
#
# dtslogger.debug(
#     f"encoding: stdout {sys.stdout.encoding} stderr {sys.stderr.encoding} "
#     f"locale {locale.getpreferredencoding()}."
# )

from .cli import DTShell
from .logging import dts_print

from .commands import DTCommandAbs, DTCommandPlaceholder
from .main import cli_main
from .exceptions import *

from .main import OtherVersions
from .checks.packages import *

# singleton
shell: Optional[DTShell] = None
