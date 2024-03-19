# -*- coding: utf-8 -*-
import dataclasses
import datetime
import os
from typing import Optional, Dict, List

DEBUG = False
DNAME = "Duckietown Shell"
DEFAULT_ROOT = os.path.expanduser("~/.duckietown/shell/")
BASH_COMPLETION_DIR = os.path.expanduser("~/.local/share/bash-completion/completions")
DTHUB_URL = os.environ.get("DTHUB_URL", "https://hub.duckietown.com")


@dataclasses.dataclass
class Distro:
    name: str
    branch: str = None
    end_of_life: Optional[datetime.date] = None
    staging: bool = False
    stable: bool = False
    tokens_supported: List[str] = dataclasses.field(default_factory=list)
    token_preferred: Optional[str] = None

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
PUSH_USER_EVENTS_TO_HUB_SECS = 60 * 60 * 1   # every 1 hour

SHELL_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROFILES_DIR = os.path.join(DEFAULT_ROOT, "profiles")

IGNORE_ENVIRONMENTS: bool = os.environ.get("IGNORE_ENVIRONMENTS", "0").lower() in ["1", "y", "yes"]

# distributions
KNOWN_DISTRIBUTIONS: Dict[str, Distro] = {
    # daffy
    "daffy": Distro(
        "daffy",
        "daffy",
        stable=True,
        # end_of_life=datetime.date(2024, 12, 31),
        tokens_supported=["dt1", "dt2"],
        token_preferred="dt1"
    ),
    "daffy-staging": Distro(
        "daffy",
        "daffy-staging",
        stable=True,
        # end_of_life=datetime.date(2024, 12, 31),
        staging=True,
        tokens_supported=["dt1", "dt2"],
        token_preferred="dt1"
    ),
    # ente
    "ente": Distro(
        "ente",
        "ente",
        stable=False,
        tokens_supported=["dt2"],
        token_preferred="dt2"
    ),
    "ente-staging": Distro(
        "ente",
        "ente-staging",
        stable=False,
        staging=True,
        tokens_supported=["dt2"],
        token_preferred="dt2"
    ),
}
SUGGESTED_DISTRIBUTION: str = "daffy"

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
DB_STATISTICS_EVENTS: str = "stats_events"
