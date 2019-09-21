import glob
import json
import os
import time
from os.path import getmtime
from typing import Dict, Optional

from git import InvalidGitRepositoryError, NoSuchPathError, Repo

from . import dtslogger
from .config import remoteurl_from_RepoInfo, RepoInfo
from .constants import CHECK_CMDS_UPDATE_EVERY_MINS
from .logging import dts_print


class InvalidRemote(Exception):
    pass


def _init_commands(commands_path: str, repo_info: RepoInfo) -> None:
    """ Raises InvalidRemote if it cannot find it"""

    dtslogger.info("Downloading commands in %s ..." % commands_path)
    # create commands repo
    commands_repo = Repo.init(commands_path)
    # the repo now exists
    remote_url = remoteurl_from_RepoInfo(repo_info)
    origin = commands_repo.create_remote("origin", remote_url)
    # check existence of `origin`
    if not origin.exists():
        msg = "The commands repository %r cannot be found. Exiting." % origin.urls
        raise InvalidRemote(msg)
    # pull data
    origin.fetch()
    branch = repo_info.branch
    commands_repo.git.checkout(branch)
    # create local.master <-> remote.master
    # commands_repo.create_head('master', origin.refs.master)
    # commands_repo.heads[branch].master.set_tracking_branch(origin.refs.master)
    # pull data
    _res = origin.pull()
    # the repo is there and there is a `origin` remote, merge
    # commands_repo.heads.master.checkout()


def check_commands_outdated(commands_path: str, repo_info: RepoInfo) -> bool:
    commands_update_check_flag = os.path.join(commands_path, ".updates-check")
    if not os.path.exists(commands_path):
        msg = "Repo does not exist."
        raise Exception(msg)
    try:
        commands_repo = Repo(commands_path)
    except (NoSuchPathError, InvalidGitRepositoryError) as e:
        # the repo does not exist, this should never happen
        msg = "I cannot read the commands repo"
        raise Exception(msg) from e

    dtslogger.info(f"looking at {commands_path}")
    # print(list(commands_repo.heads))
    local_sha = commands_repo.heads[repo_info.branch].commit.hexsha
    # get remote SHA
    use_cached_sha = False
    if os.path.exists(commands_update_check_flag) and os.path.isfile(
        commands_update_check_flag
    ):
        now = time.time()
        last_time_checked = getmtime(commands_update_check_flag)
        use_cached_sha = now - last_time_checked < CHECK_CMDS_UPDATE_EVERY_MINS * 60
    # get remote SHA
    if use_cached_sha:
        # no need to check now
        with open(commands_update_check_flag, "r") as fp:
            try:
                cached_check = json.load(fp)
            except ValueError:
                return False
            remote_sha = cached_check["remote"]
    else:
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
    try:
        commands_repo = Repo(commands_path)
    except (NoSuchPathError, InvalidGitRepositoryError):
        # the repo does not exist
        if not _init_commands(commands_path, repo_info):
            return False
        commands_repo = Repo(commands_path)

    # the repo exists
    dts_print("Updating commands...")
    origin = commands_repo.remote("origin")
    # check existence of `origin`
    if not origin.exists():
        dtslogger.error(
            "The commands repository %r cannot be found. Exiting." % origin.urls
        )
        return False
    _res = origin.pull()
    # pull data from remote.master to local.master
    branch = repo_info.branch
    commands_repo.git.checkout(branch)

    # # update all submodules
    # print('Updating libraries...', end='')
    # try:
    #     commands_repo.submodule_update(recursive=True, to_latest_revision=False)
    # except Exception as e:
    #     msg = 'Could not update libraries: %s' % e
    #     dtslogger.error(msg)

    # everything should be fine
    dts_print("OK")
    # cache current (local=remote) SHA
    current_sha = commands_repo.heads[branch].commit.hexsha
    save_update_check_flag(commands_path, current_sha)
    # return success
    return True


def _get_commands(path: str, lvl=0, all_commands=False) -> Optional[Dict[str, object]]:
    entries = glob.glob(os.path.join(path, "*"))
    files = [os.path.basename(e) for e in entries if os.path.isfile(e)]
    dirs = [
        e
        for e in entries
        if os.path.isdir(e) and (lvl > 0 or os.path.basename(e) != "lib")
    ]
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
