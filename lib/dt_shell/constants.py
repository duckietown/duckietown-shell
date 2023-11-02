# -*- coding: utf-8 -*-
import dataclasses
import datetime
import os
from typing import Optional, Dict

DEBUG = False
DNAME = "Duckietown Shell"
DEFAULT_ROOT = os.path.expanduser("~/.duckietown/shell/")
BASH_COMPLETION_DIR = os.path.expanduser("~/.local/share/bash-completion/completions")
DTHUB_URL = os.environ.get("DTHUB_URL", "https://hub.duckietown.com")
AUTH_URL = os.environ.get("DTAUTH_URL", "https://auth.duckietown.com")


@dataclasses.dataclass
class Distro:
    name: str
    branch: str = None
    end_of_life: Optional[datetime.date] = None
    staging: bool = False

    def __post_init__(self):
        # if the branch is not given then it takes the distro name
        if self.branch is None:
            self.branch = self.name

    @property
    def end_of_life_fmt(self, fmt: str = "%d %B %Y") -> str:
        if self.end_of_life is None:
            return ""
        return self.end_of_life.strftime(fmt)

    def as_dict(self) -> dict:
        return dataclasses.asdict(self)


class DTShellConstants:
    PROFILE: Optional[str] = None
    ROOT: str = os.path.expanduser(os.environ.get("DTSHELL_ROOT", DEFAULT_ROOT))
    DEBUG: bool = False
    VERBOSE: bool = False
    QUIET: bool = False


# commands update
CHECK_CMDS_UPDATE_MINS = 5
CHECK_BILLBOARD_UPDATE_SECS = 60 * 60 * 24   # every 24 hours
CHECK_SHELL_TOKEN_SECS = 60 * 15   # every 15 minutes

SHELL_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILES_DIR = os.path.join(DEFAULT_ROOT, "profiles")

IGNORE_ENVIRONMENTS: bool = os.environ.get("IGNORE_ENVIRONMENTS", "0").lower() in ["1", "y", "yes"]

# distributions
KNOWN_DISTRIBUTIONS: Dict[str, Distro] = {
    # daffy
    "daffy": Distro("daffy", "daffy", end_of_life=datetime.date(2024, 3, 31)),
    "daffy-staging": Distro("daffy", "daffy-staging", end_of_life=datetime.date(2024, 3, 31), staging=True),
    # ente
    "ente": Distro("ente", "ente"),
    "ente-staging": Distro("ente", "ente-staging", staging=True),
    # temporary
    # TODO: remove
    "v6": Distro("v6", "v6", staging=True),
}
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
DB_MIGRATIONS: str = "migrations"
DB_UPDATES_CHECK: str = "updates_check"
DB_BILLBOARDS: str = "billboards"
