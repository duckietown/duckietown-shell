import grp
import os
import subprocess
import sys
from typing import List, Optional

from shutil import which

from ..exceptions import InvalidEnvironment, UserError
from .. import logger


def running_with_sudo() -> bool:
    return os.geteuid() == 0


def abort_if_running_with_sudo() -> None:
    if running_with_sudo():
        if "CIRCLECI" in os.environ:
            return
        msg = """\
Do not run dts using "sudo".'

As a matter of fact, do not run anything with "sudo" unless instructed to do so.\
"""
        raise UserError(msg)


def check_docker_environment():
    """Returns docker client"""
    check_executable_exists("docker")

    check_user_in_docker_group()
    #
    # if on_linux():
    #
    #     if username != 'root':
    #         check_user_in_docker_group()
    #     # print('checked groups')
    # else:
    #     logger.debug('skipping env check because not on Linux')

    try:
        import docker
    except Exception as e:
        msg = "Could not import package docker:\n%s" % e
        msg += "\n\nYou need to install the package"
        raise InvalidEnvironment(msg)

    if "DOCKER_HOST" in os.environ:
        msg = 'Note that the variable DOCKER_HOST is set to "%s"' % os.environ["DOCKER_HOST"]
        logger.warning(msg)

    try:
        # noinspection PyUnresolvedReferences
        client = docker.from_env()

    except Exception as e:
        msg = "I cannot communicate with Docker:\n%s" % e
        msg += "\n\nMake sure the docker service is running."
        raise InvalidEnvironment(msg)

    return client


def on_linux() -> bool:
    return sys.platform.startswith("linux")


def check_executable_exists(cmdname: str) -> None:
    p = which(cmdname)
    if p is None:
        msg = 'Could not find executable "%s".' % cmdname
        raise InvalidEnvironment(msg)


def check_user_in_docker_group() -> None:
    # first, let's see if there exists a group "docker"
    group_names = [g.gr_name for g in grp.getgrall()]
    G = "docker"
    if G not in group_names:
        pass
    else:
        group_id = grp.getgrnam(G).gr_gid
        my_groups = os.getgroups()
        if group_id not in my_groups:
            msg = 'My groups are %s and "%s" group is %s ' % (my_groups, G, group_id)
            msg += "\n\nNote that when you add a user to a group, you need to login in and out."
            # logger.debug(msg)


def get_active_groups(username: Optional[str] = None) -> List[str]:
    cmd = ["groups"]

    if username:
        cmd.append(username)

    try:
        stdout = subprocess.check_output(["groups"])
    except subprocess.CalledProcessError as e:
        raise Exception(str(e))
    active_groups = stdout.decode().split()

    return active_groups
