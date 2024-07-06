import json
import traceback
from dataclasses import dataclass
from typing import Optional, List

from dt_shell_cli import logger
from ..exceptions import RunCommandException
from ..checks.version import get_url
from ..constants import DEFAULT_COMMAND_SET_REPOSITORY, DTShellConstants
from ..utils import run_cmd, provider_username_project_from_git_url, indent_block


@dataclass
class CommandsRepository:
    username: str
    project: str
    branch: str
    location: Optional[str] = None
    use_ssh: bool = False
    provider: str = "github.com"

    @property
    def remoteurl(self) -> str:
        if self.use_ssh:
            return f"git@{self.provider}:{self.username}/{self.project}"
        return f"https://{self.provider}/{self.username}/{self.project}"

    @property
    def apiurl(self) -> str:
        if self.provider != "github.com":
            raise ValueError("Only github.com is supported")
        return f"https://api.github.com/repos/{self.username}/{self.project}"

    @property
    def apiurl_with_branch(self) -> str:
        if self.provider != "github.com":
            raise ValueError("Only github.com is supported")
        return f"https://api.github.com/repos/{self.username}/{self.project}/branches/{self.branch}"

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "username": self.username,
            "project": self.project,
            "branch": self.branch,
            "location": self.location,
            "url": self.remoteurl,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'CommandsRepository':
        return CommandsRepository(
            username=data["username"],
            project=data["project"],
            branch=data["branch"],
            location=data.get("location", None),
            use_ssh=data["url"].startswith("git@"),
            provider=data.get("provider", "github.com")
        )

    def remote_sha(self) -> Optional[str]:
        # Get the remote sha from GitHub
        logger.info("Fetching remote SHA from github.com ...")
        if self.use_ssh:
            logger.warning(f"Command set '{self.username}/{self.project}' is using SSH. Cannot fetch remote SHA.")
            return None
        else:
            remote_url: str = self.apiurl_with_branch
            # contact github
            try:
                content = get_url(remote_url)
            except Exception:
                if DTShellConstants.VERBOSE:
                    traceback.print_exc()
                logger.debug(f"URL called: {remote_url}")
                logger.warning(f"An error occurred while fetching the remote SHA for repository {self.remoteurl}")
                return None
            # parse output
            try:
                data = json.loads(content)
                return data["commit"]["sha"]
            except Exception:
                if DTShellConstants.VERBOSE:
                    traceback.print_exc()
                logger.debug(f"URL called: {remote_url}\n"
                             f"Object returned by github:\n\n{indent_block(content)}")
                logger.warning(f"An error occurred while fetching the remote SHA for repository {self.remoteurl}")
                return None

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

    @staticmethod
    def head_tag(path: str) -> Optional[str]:
        try:
            tags: str = run_cmd(["git", "-C", path, "describe", "--exact-match", "--tags", "HEAD"])
        except RunCommandException as e:
            if e.stderr is not None and "no tag exactly matches" in e.stderr:
                # just not an exact match
                return None
            if DTShellConstants.VERBOSE:
                traceback.print_exc()
            return None
        except Exception:
            if DTShellConstants.VERBOSE:
                traceback.print_exc()
            return None
        # ---
        tags: List[str] = tags.strip().split("\n")
        if not tags:
            return None
        return tags[0]

    @staticmethod
    def closest_tag(path: str) -> Optional[str]:
        try:
            tags: Optional[str] = run_cmd(["git", "-C", path, "tag", "--merged"])
        except Exception:
            if DTShellConstants.VERBOSE:
                traceback.print_exc()
            return None
        # no tgs
        if tags is None:
            return None
        # ---
        tags: List[str] = tags.strip().split("\n")
        if not tags:
            return None
        return tags[-1]

    @classmethod
    def from_remoteurl(cls, remoteurl: str, branch: str, location: Optional[str] = None) -> 'CommandsRepository':
        provider, username, project = provider_username_project_from_git_url(remoteurl)
        return CommandsRepository(
            username=username,
            project=project,
            branch=branch,
            provider=provider,
            location=location,
            use_ssh=remoteurl.startswith("git@")
        )
