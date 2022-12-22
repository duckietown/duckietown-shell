import glob
import json
import os
import time
from os.path import getmtime
from typing import Dict, Optional

from . import dtslogger
from .config import remoteurl_from_RepoInfo, RepoInfo
from .exceptions import UserError
from .logging import dts_print
from .update_utils import update_cached_commands
from .utils import run_cmd


class InvalidRemote(Exception):
    pass


def _init_commands(commands_path: str, repo_info: RepoInfo) -> bool:
    """Raises InvalidRemote if it cannot find it"""
    try:
        dtslogger.info("Downloading Duckietown shell commands in %s ..." % commands_path)
        # clone the repo
        remote_url = remoteurl_from_RepoInfo(repo_info)
        run_cmd(["git", "clone", "-b", repo_info.branch, "--recurse-submodules", remote_url, commands_path])
    except Exception as e:
        # Excepts as InvalidRemote
        dtslogger.error(f"Unable to clone the repo at '{remote_url}'. {str(e)}.")
        return False


def _ensure_commands_exist(commands_path: str, repo_info: RepoInfo) -> bool:
    # clone the commands if necessary
    if not os.path.exists(commands_path):
        _init_commands(commands_path, repo_info)
    # make sure the commands exist
    if not os.path.exists(commands_path):
        raise UserError(f"Commands not found at '{commands_path}'.")


def _ensure_commands_updated(commands_path: str, repo_info: RepoInfo) -> bool:
    return update_cached_commands(commands_path, repo_info)


def _get_commands(path: str, lvl=0, all_commands=False) -> Optional[Dict[str, object]]:
    entries = glob.glob(os.path.join(path, "*"))
    files = [os.path.basename(e) for e in entries if os.path.isfile(e)]
    dirs = [e for e in entries if os.path.isdir(e) and (lvl > 0 or os.path.basename(e) != "lib")]
    # base case: empty dir
    if "command.py" not in files and not dirs:
        return None
    if (
        not all_commands
        and lvl == 1
        and ("installed.flag" not in files and "installed.user.flag" not in files)
    ):
        return None
    # check subcommands
    subcmds = {}
    for d in dirs:
        f = _get_commands(d, lvl + 1, all_commands)
        if f is not None:
            subcmds[os.path.basename(d)] = f
    # return
    if "command.py" not in files and not subcmds:
        return None
    # ---
    return subcmds
