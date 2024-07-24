# -*- coding: utf-8 -*-
import logging
import pathlib
import warnings

warnings.filterwarnings(action='ignore', module='.*paramiko.*')

# ===> COMPATIBILITY
# these are only for older versions of the commands, we will drop these with the shell v7
COMPATIBILITY_DIR = str(pathlib.Path(__file__).parent.joinpath("compatibility").resolve())
__path__ += [COMPATIBILITY_DIR]

from .compatibility import duckietown_tokens
from .compatibility import OtherVersions
from .compatibility.env_checks import check_package_version
# <=== COMPATIBILITY

logging.basicConfig()

from dt_shell_cli import logger
from dt_shell_cli.utils import install_colored_logs

# logger dedicated to the commands
dtslogger = logging.getLogger("dts")
install_colored_logs(logger=dtslogger)
dtslogger.setLevel(logging.INFO)

__version__ = "6.0.17"

import sys

if sys.version_info < (3, 6):
    msg = f"! duckietown-shell works with Python 3.6 and later !.\nDetected {sys.version}."
    logger.error(msg)
    sys.exit(2)

from .shell import DTShell

from .commands import DTCommandAbs, DTCommandPlaceholder
from .exceptions import *
from typing import Optional

# singleton
shell: Optional[DTShell] = None
