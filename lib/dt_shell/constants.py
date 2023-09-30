# -*- coding: utf-8 -*-
import dataclasses
import datetime
import os
from typing import Optional, List

import termcolor

from . import __version__

DEBUG = False
DEFAULT_ROOT = os.path.expanduser("~/.duckietown/shell/")
DUCKIETOWN_TOKEN_URL = "https://hub.duckietown.com/token"
SHELL_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILES_DIR = os.path.join(DEFAULT_ROOT, "profiles")
DEFAULT_COMMAND_SET_REPOSITORY = {"username": "duckietown", "project": "duckietown-shell-commands"}


@dataclasses.dataclass
class Distro:
    name: str
    end_of_life: Optional[datetime.date] = None

    @property
    def end_of_life_fmt(self, fmt: str = "%d %B %Y") -> str:
        if self.end_of_life is None:
            return ""
        return self.end_of_life.strftime(fmt)


KNOWN_DISTRIBUTIONS: List[Distro] = [
    Distro("daffy", end_of_life=datetime.date(2024, 3, 31)),
    Distro("ente"),
]
SUGGESTED_DISTRIBUTION: str = "ente"


class DTShellConstants:
    PROFILE: Optional[str] = None
    ROOT = os.path.expanduser(os.environ.get("DTSHELL_ROOT", DEFAULT_ROOT))


CHECK_CMDS_UPDATE_MINS = 5

DNAME = "Duckietown Shell"


def INTRO(extra: Optional[str] = None) -> str:
    return """

Welcome to the interactive {Duckietown} ({version}).
{extra}
Type "help" or "?" to list commands.

""".format(
        Duckietown=termcolor.colored(DNAME, "yellow", attrs=["bold"]), version=__version__, extra=extra or ""
    ).lstrip()
