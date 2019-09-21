import grp
import os
import subprocess
import sys
from typing import List, Optional

from whichcraft import which

from . import dtslogger
from .config import read_shell_config
from .exceptions import InvalidEnvironment, UserError


def running_with_sudo() -> bool:
    if "SUDO_USER" in os.environ:
        return True
    return False


def abort_if_running_with_sudo() -> None:
    if running_with_sudo():
        msg = """\
Do not run dts using "sudo".'

As a matter of fact, do not run anything with "sudo" unless instructed to do so.\
"""
        raise UserError(msg)


def check_docker_environment():
    """ Returns docker client """

    from . import dtslogger

    # dtslogger.debug('Checking docker environment for user %s' % username)

    check_executable_exists("docker")

    check_user_in_docker_group()
    #
    # if on_linux():
    #
    #     if username != 'root':
    #         check_user_in_docker_group()
    #     # print('checked groups')
    # else:
    #     dtslogger.debug('skipping env check because not on Linux')

    try:
        import docker
    except Exception as e:
        msg = "Could not import package docker:\n%s" % e
        msg += "\n\nYou need to install the package"
        raise InvalidEnvironment(msg)

    if "DOCKER_HOST" in os.environ:
        msg = (
            'Note that the variable DOCKER_HOST is set to "%s"'
            % os.environ["DOCKER_HOST"]
        )
        dtslogger.warning(msg)

    try:
        # noinspection PyUnresolvedReferences
        client = docker.from_env()

        _containers = client.containers.list(filters=dict(status="running"))

        # dtslogger.debug(json.dumps(client.info(), indent=4))

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
        msg = "No group %s defined." % G
        # dtslogger.warning(msg)
    else:
        group_id = grp.getgrnam(G).gr_gid
        my_groups = os.getgroups()
        if group_id not in my_groups:
            msg = 'My groups are %s and "%s" group is %s ' % (my_groups, G, group_id)
            msg += "\n\nNote that when you add a user to a group, you need to login in and out."
            dtslogger.debug(msg)
    #
    #     active_groups = get_active_groups(username=None)
    #
    # if name not in active_groups:
    #     msg = 'The user is not in group "%s".' % name
    #     msg += '\n\nIt belongs to groups: %s.' % u", ".join(sorted(active_groups))
    #
    #     msg += '\n\nNote that when you add a user to a group, you need to login in and out.'
    #
    #     if True:
    #         dtslogger.warning(msg)
    #     else:
    #         raise InvalidEnvironment(msg)


def get_active_groups(username: Optional[str] = None) -> List[str]:
    cmd = ["groups"]

    if username:
        cmd.append(username)

    try:
        stdout = subprocess.check_output(["groups"])
        # res = system_cmd_result('.', cmd,
        #                         display_stdout=False,
        #                         display_stderr=False,
        #                         raise_on_error=True,
        #                         capture_keyboard_interrupt=False,
        #                         env=None)
    except subprocess.CalledProcessError as e:
        raise Exception(str(e))
    active_groups = stdout.decode().split()

    return active_groups


def get_dockerhub_username() -> str:
    """ raise InvalidEnvironment """
    try:
        shell_config = read_shell_config()
    except Exception:
        msg = "Please set docker username using\n\n dts challenges config --docker-username <USERNAME>"
        raise InvalidEnvironment(msg)
    #
    # if shell is None:
    #     from .cli import DTShell
    #     shell = DTShell()
    # k = DTShellConstants.CONFIG_DOCKER_USERNAME
    # if k not in shell.config:

    if shell_config.docker_username is None:
        msg = "Please set docker username using\n\n dts challenges config --docker-username <USERNAME>"
        raise InvalidEnvironment(msg)

    return shell_config.docker_username
