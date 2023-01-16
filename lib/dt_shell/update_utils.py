import json
import os
import time

from . import dtslogger, version_check
from . import version_check
from .config import remoteurl_from_RepoInfo, RepoInfo
from .constants import CHECK_CMDS_UPDATE_MINS
from .exceptions import UserError
from .utils import run_cmd


def commands_need_update(commands_path: str, repo_info: RepoInfo) -> bool:
    need_update = False
    # Get the current repo info
    commands_update_check_flag = os.path.join(commands_path, ".updates-check")

    # Check if it's time to check for an update
    if os.path.exists(commands_update_check_flag) and os.path.isfile(commands_update_check_flag):
        now = time.time()
        last_time_checked = os.path.getmtime(commands_update_check_flag)
        use_cached_commands = now - last_time_checked < CHECK_CMDS_UPDATE_MINS * 60
    else:  # Save the initial .update flag
        local_sha: str = run_cmd(["git", "-C", commands_path, "rev-parse", "HEAD"])
        # noinspection PyTypeChecker
        local_sha = next(filter(len, local_sha.split("\n")))
        save_update_check_flag(commands_path, local_sha)
        return False

    # Check for an updated remote
    if not use_cached_commands:
        # Get the local sha from file (ok if oos from manual pull)
        with open(commands_update_check_flag, "r") as fp:
            try:
                cached_check = json.load(fp)
            except ValueError:
                return False
            local_sha = cached_check["remote"]

        # Get the remote sha from GitHub
        dtslogger.info("Fetching remote SHA from github.com ...")
        remote_url: str = "https://api.github.com/repos/%s/%s/branches/%s" % (
            repo_info.username,
            repo_info.project,
            repo_info.branch,
        )
        try:
            content = version_check.get_url(remote_url)
            data = json.loads(content)
            remote_sha = data["commit"]["sha"]
        except Exception as e:
            dtslogger.error(str(e))
            return False

        # check if we need to update
        need_update = local_sha != remote_sha
        # touch flag to reset update check time
        touch_update_check_flag(commands_path)

    return need_update


def save_update_check_flag(commands_path: str, sha: str) -> None:
    commands_update_check_flag = os.path.join(commands_path, ".updates-check")
    with open(commands_update_check_flag, "w") as fp:
        json.dump({"remote": sha}, fp)


def touch_update_check_flag(commands_path: str) -> None:
    commands_update_check_flag = os.path.join(commands_path, ".updates-check")
    with open(commands_update_check_flag, "a"):
        os.utime(commands_update_check_flag, None)


def update_cached_commands(commands_path: str, repo_info: RepoInfo) -> bool:
    if not os.path.exists(commands_path) and os.path.isdir(commands_path):
        raise UserError(f"There is no existing commands directory in '{commands_path}'.")

    # Check for shell commands repo updates
    dtslogger.info("Checking for updates in the Duckietown shell commands repo...")
    if commands_need_update(commands_path, repo_info):
        dtslogger.info("The Duckietown shell commands have available updates. Attempting to pull them.")
        dtslogger.debug(f"Updating Duckietown shell commands at '{commands_path}'...")
        wait_on_retry_secs = 4
        th = {2: "nd", 3: "rd", 4: "th"}
        for trial in range(3):
            try:
                run_cmd(["git", "-C", commands_path, "pull", "--recurse-submodules", "origin", repo_info.branch])
                dtslogger.debug(f"Updated Duckietown shell commands in '{commands_path}'.")
                dtslogger.info(f"Duckietown shell commands successfully updated!")
            except RuntimeError as e:
                dtslogger.error(str(e))
                dtslogger.warning(
                    "An error occurred while pulling the updated commands. Retrying for "
                    f"the {trial + 2}-{th[trial + 2]} in {wait_on_retry_secs} seconds."
                )
                time.sleep(wait_on_retry_secs)
            else:
                break
        run_cmd(["git", "-C", commands_path, "submodule", "update"])

        # Get HEAD sha after update and save
        current_sha: str = run_cmd(["git", "-C", commands_path, "rev-parse", "HEAD"])
        # noinspection PyTypeChecker
        current_sha = next(filter(len, current_sha.split("\n")))
        save_update_check_flag(commands_path, current_sha)
        return True  # Done updating
    else:
        dtslogger.info(f"Duckietown shell commands are up-to-date.")
        return False
