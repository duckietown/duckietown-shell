import argparse
import os
from typing import List, cast, Optional

import requests

from dt_shell import DTCommandAbs, DTShell, dtslogger, RunCommandException
from dt_shell.commands import CommandSet
from dt_shell.commands.repository import CommandsRepository
from dt_shell.constants import DB_USER_COMMAND_SETS_REPOSITORIES
from dt_shell.database import DTShellDatabase
from dt_shell.utils import run_cmd


class DTCommand(DTCommandAbs):
    help = "Installs a new command set."

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        parsed: argparse.Namespace = DTCommand.parser.parse_args(args)
        # ---
        url: Optional[str] = None
        # sanitize the repository URL
        parsed.repository = parsed.repository.strip("/")
        if parsed.repository.endswith(".git"):
            parsed.repository = parsed.repository[:-4]
        # - public URL
        if ":" not in parsed.repository:
            dtslogger.debug(f"Checking if '{parsed.repository}' is a public repository.")
            # assume the URL is fully qualified
            public_url = parsed.repository
            # add the protocol if missing
            if cast(str, parsed.repository).count("/") == 2:
                # matches the pattern "server/owner/repo"
                public_url = f"https://{public_url}"
            # default to github.com
            if not public_url.startswith('http'):
                public_url = f"https://github.com/{parsed.repository}"
            # ---
            url = public_url
            dtslogger.debug(f"Assuming the URL is the following: {url}")
            # try to reach the repository at the public URL
            repo: CommandsRepository = CommandsRepository.from_remoteurl(url, parsed.branch)
            try:
                dtslogger.debug(f"> HEAD {repo.apiurl}")
                requests.head(repo.apiurl, timeout=5).raise_for_status()
                dtslogger.info(f"Repository found at {public_url}.")
            except requests.RequestException:
                dtslogger.info(f"Repository not found at {public_url}. Assuming it is a private repository.")
                url = None

        if ":" in parsed.repository or url is None:
            # assume the URL is a private repository
            dtslogger.debug(f"Assuming '{parsed.repository}' is a private repository.")
            # - private URL
            private_url = parsed.repository
            # add the protocol if missing
            if ":" in parsed.repository:
                if not private_url.startswith('git@'):
                    private_url = f"git@{private_url}"
            else:
                private_url = f"git@github.com:{parsed.repository}"
            # ---
            url = private_url
            dtslogger.debug(f"Assuming the URL is the following: {url}")
            # check if SSH is configured properly
            dtslogger.debug("Checking if SSH is configured properly.")
            try:
                cmd = ["ssh", "-T", "git@github.com"]
                dtslogger.debug(f"$ {' '.join(cmd)}")
                run_cmd(cmd)
            except RunCommandException as e:
                if e.exit_code == 1 and "successfully" in e.stderr.lower():
                    dtslogger.info("SSH communication with GitHub is successful.")
                else:
                    dtslogger.error("SSH is not configured properly. The command 'ssh -T git@github.com' fails.")
                    return
        # ---
        # define command set properties
        repository: CommandsRepository = CommandsRepository.from_remoteurl(url, parsed.branch)
        name: str = f"{repository.username}__{repository.project}"
        path: str = os.path.join(shell.profile.path, "commands", name)
        # create command set
        cs: CommandSet = CommandSet(
            name=name,
            path=path,
            profile=shell.profile,
            repository=repository,
        )
        # open the database
        db: DTShellDatabase[dict] = shell.profile.database(DB_USER_COMMAND_SETS_REPOSITORIES)
        # make sure the command set is not already installed
        if db.contains(cs.name):
            dtslogger.info(f"Command set '{cs.name}' is already installed.")
            return
        # install command set
        dtslogger.info(f"Downloading command set '{cs.name}'...")
        cs.ensure_commands_exist()
        # add commands to the list of user command sets
        dtslogger.debug(f"Adding command set '{cs.name}' to the list of user command sets.")
        db.set(cs.name, cs.repository.as_dict())
        # done
        dtslogger.info(f"Command set '{cs.name}' installed successfully.")

    @staticmethod
    def complete(shell: DTShell, word: str, line: str) -> List[str]:
        return []
