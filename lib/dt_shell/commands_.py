import glob
import json
import os
import time
from os.path import getmtime
from typing import Dict, Optional

from . import dtslogger
from .config import remoteurl_from_RepoInfo, RepoInfo
from .constants import CHECK_CMDS_UPDATE_EVERY_MINS
from .logging import dts_print
from .utils import run_cmd


class InvalidRemote(Exception):
    pass


def _init_commands(commands_path: str, repo_info: RepoInfo) -> None:
    """Raises InvalidRemote if it cannot find it"""

    dtslogger.info("Downloading commands in %s ..." % commands_path)
    # the repo now exists
    remote_url = remoteurl_from_RepoInfo(repo_info)
    run_cmd(["git", "clone", "-b", repo_info.branch, "--recurse-submodules", remote_url, commands_path])


def check_commands_outdated(commands_path: str, repo_info: RepoInfo) -> bool:
    commands_update_check_flag = os.path.join(commands_path, ".updates-check")
    if not os.path.exists(commands_path):
        msg = "Repo does not exist."
        raise Exception(msg)

    dtslogger.info(f"looking at {commands_path}")
    local_sha = run_cmd(["git", "-C", commands_path, "rev-parse", "HEAD"])
    # get the first non-empty line
    local_sha = list(filter(len, local_sha.split("\n")))[0]
    # get remote SHA
    use_cached_sha = False
    if os.path.exists(commands_update_check_flag) and os.path.isfile(commands_update_check_flag):
        now = time.time()
        last_time_checked = getmtime(commands_update_check_flag)
        use_cached_sha = now - last_time_checked < CHECK_CMDS_UPDATE_EVERY_MINS * 60
    # get remote SHA
    if use_cached_sha:
        dtslogger.debug("Using cached remote SHA for command update check.")
        # no need to check now
        with open(commands_update_check_flag, "r") as fp:
            try:
                cached_check = json.load(fp)
            except ValueError:
                return False
            remote_sha = cached_check["remote"]
    else:
        dtslogger.debug("Fetching remote SHA for command update check from github.com")
        url = "https://api.github.com/repos/%s/%s/branches/%s" % (
            repo_info.username,
            repo_info.project,
            repo_info.branch,
        )
        try:
            from .version_check import get_url

            content = get_url(url)
            data = json.loads(content)
            remote_sha = data["commit"]["sha"]
        except BaseException as e:
            from .utils import format_exception

            dtslogger.error(format_exception(e))
            return False
    # check if we need to update
    need_update = local_sha != remote_sha
    if need_update:
        msg = """

An updated version of the commands is available.

Attempting auto-update.

        """
        dts_print(msg, color="yellow", attrs=["bold"])

        try:
            update_commands(commands_path, repo_info)

            # cache remote SHA
            if not use_cached_sha:
                save_update_check_flag(commands_path, remote_sha)

        except BaseException as e:
            from .utils import format_exception

            dtslogger.error(format_exception(e))

    # return success
    return True


def save_update_check_flag(commands_path: str, remote_sha: str) -> None:
    commands_update_check_flag = os.path.join(commands_path, ".updates-check")
    with open(commands_update_check_flag, "w") as fp:
        json.dump({"remote": remote_sha}, fp)


def update_commands(commands_path: str, repo_info: RepoInfo) -> bool:
    # create commands repo
    if not os.path.exists(commands_path):
        # the repo does not exist
        if not _init_commands(commands_path, repo_info):
            return False
    # the repo now exists
    dts_print("Updating commands...")
    # pull from origin (try 3 times)
    for trial in range(3):
        try:
            run_cmd(["git", "-C", commands_path, "pull", "--recurse-submodules", "origin", repo_info.branch])
        except RuntimeError as e:
            dtslogger.error(str(e))
            wait_time = 4
            th = {2: "nd", 3: "rd", 4: "th"}
            dtslogger.warning(
                "An error occurred while pulling the updated commands. Retrying for "
                f"the {trial + 2}-{th[trial + 2]} in {wait_time} seconds."
            )
            time.sleep(wait_time)
        else:
            break
    # update submodules
    run_cmd(["git", "-C", commands_path, "submodule", "update"])
    # get HEAD sha
    current_sha = run_cmd(["git", "-C", commands_path, "rev-parse", "HEAD"])
    # everything should be fine
    dts_print("OK")
    # cache current (local=remote) SHA
    save_update_check_flag(commands_path, current_sha)
    # return success
    return True


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
