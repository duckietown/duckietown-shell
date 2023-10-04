# -*- coding: utf-8 -*-
import dataclasses
import datetime
import os
from typing import Optional, List

import termcolor

from . import __version__

DEBUG = False
DNAME = "Duckietown Shell"
DEFAULT_ROOT = os.path.expanduser("~/.duckietown/shell/")


@dataclasses.dataclass
class Distro:
    name: str
    end_of_life: Optional[datetime.date] = None

    @property
    def end_of_life_fmt(self, fmt: str = "%d %B %Y") -> str:
        if self.end_of_life is None:
            return ""
        return self.end_of_life.strftime(fmt)


class DTShellConstants:
    PROFILE: Optional[str] = None
    ROOT: str = os.path.expanduser(os.environ.get("DTSHELL_ROOT", DEFAULT_ROOT))
    DEBUG: bool = False
    VERBOSE: bool = False
    QUIET: bool = False


# commands update
CHECK_CMDS_UPDATE_MINS = 5

SHELL_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
SHELL_CLI_LIB_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_PROFILES_DIR = os.path.join(DEFAULT_ROOT, "profiles")

IGNORE_ENVIRONMENTS: bool = os.environ.get("IGNORE_ENVIRONMENTS", "0").lower() in ["1", "y", "yes"]

# distributions
KNOWN_DISTRIBUTIONS: List[Distro] = [
    Distro("daffy", end_of_life=datetime.date(2024, 3, 31)),
    Distro("ente"),
]
SUGGESTED_DISTRIBUTION: str = "ente"

# command set
EMBEDDED_COMMAND_SET_NAME: str = "embedded"
DEFAULT_COMMAND_SET_REPOSITORY = {
    "username": "duckietown",
    "project": "duckietown-shell-commands",
    "branch": SUGGESTED_DISTRIBUTION
}

# URLs
DUCKIETOWN_TOKEN_URL = "https://hub.duckietown.com/token"

# read requirements list embedded as asset into the release
SHELL_REQUIREMENTS_LIST: str = os.path.join(os.path.dirname(__file__), "assets", "requirements.txt")
assert os.path.exists(SHELL_REQUIREMENTS_LIST)

# database names
DB_PROFILES: str = "profiles"
DB_SETTINGS: str = "settings"
DB_SECRETS: str = "secrets"
DB_SECRETS_DOCKER: str = "secrets_docker"
DB_COMMAND_SET_UPDATES_CHECK: str = "command_sets_updates_check"
DB_INSTALLED_DEPENDENCIES: str = "installed_dependencies"
DB_USER_COMMAND_SETS_REPOSITORIES: str = "user_command_sets_repositories"


def INTRO(extra: Optional[str] = None) -> str:
    return """

Welcome to the interactive {Duckietown} ({version}).
{extra}
Type "help" or "?" to list commands.

""".format(
        Duckietown=termcolor.colored(DNAME, "yellow", attrs=["bold"]), version=__version__, extra=extra or ""
    ).lstrip()
