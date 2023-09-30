from dataclasses import dataclass
from typing import Optional

from ..constants import DEFAULT_COMMAND_SET_REPOSITORY
from ..utils import run_cmd, provider_username_project_from_git_url


@dataclass
class CommandsRepository:
    username: str
    project: str
    branch: Optional[str] = None
    location: Optional[str] = None

    def remoteurl(self) -> str:
        return f"https://github.com/{self.username}/{self.username}"

    @classmethod
    def given_distro(cls, distro: str) -> 'CommandsRepository':
        return CommandsRepository(
            **DEFAULT_COMMAND_SET_REPOSITORY,
            branch=distro
        )

    @classmethod
    def from_file_system(cls, path: str, location: Optional[str] = None) -> 'CommandsRepository':
        origin_url = run_cmd(["git", "-C", path, "config", "--get", "remote.origin.url"])
        _, username, project = provider_username_project_from_git_url(origin_url)
        branch = run_cmd(["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"])
        return CommandsRepository(username, project, branch, location=location)
