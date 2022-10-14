import grp
import os
import subprocess
import sys
from typing import List, Optional, Tuple

from whichcraft import which

from .config import read_shell_config
from .exceptions import InvalidEnvironment, UserError


def running_with_sudo() -> bool:
    return os.geteuid() == 0


def abort_if_running_with_sudo() -> None:
    if running_with_sudo():
        msg = """\
Do not run dts using "sudo".'

As a matter of fact, do not run anything with "sudo" unless instructed to do so.\
"""
        raise UserError(msg)


def check_docker_environment():
    """Returns docker client"""

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
        msg = 'Note that the variable DOCKER_HOST is set to "%s"' % os.environ["DOCKER_HOST"]
        dtslogger.warning(msg)

    try:
        # noinspection PyUnresolvedReferences
        client = docker.from_env()

        # TODO: why are we doing this? It seems expensive and useless
        # _containers = client.containers.list(filters=dict(status="running"))

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
        pass
    else:
        group_id = grp.getgrnam(G).gr_gid
        my_groups = os.getgroups()
        if group_id not in my_groups:
            msg = 'My groups are %s and "%s" group is %s ' % (my_groups, G, group_id)
            msg += "\n\nNote that when you add a user to a group, you need to login in and out."
            # dtslogger.debug(msg)


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


def get_dockerhub_username() -> str:
    """raise InvalidEnvironment"""

    msg = """
        Please set docker username using
         
            dts challenges config --docker-username <USERNAME>
            
    """
    try:
        shell_config = read_shell_config()
    except Exception:
        raise

    if shell_config.docker_username is None:
        raise InvalidEnvironment(msg)

    return shell_config.docker_username


def get_dockerhub_username_and_password() -> Tuple[str, str]:
    """raise InvalidEnvironment"""
    try:
        shell_config = read_shell_config()
    except Exception:
        raise

    if shell_config.docker_username is None:
        msg = """
    Please set DockerHub username and password/token using:
    
       dts challenges config --docker-username <USERNAME> --docker-password <PASSWORD or DOCKERHUB TOKEN>
       
    You can use your DockerHub password or use a token that you can obtain at 
    
        https://hub.docker.com/settings/security              
        
    (note: this is not the Duckietown token)
    """

        raise InvalidEnvironment(msg)

    elif shell_config.docker_password is None:
        msg = """
   Please set DockerHub username and password/token using:

       dts challenges config --docker-password <PASSWORD or DOCKERHUB TOKEN>
    
    You can use your DockerHub password or use a DockerHub token that you can obtain at 
        
            https://hub.docker.com/settings/security 
            
    (note: this is not the Duckietown token)
       """

        raise InvalidEnvironment(msg)

    return shell_config.docker_username, shell_config.docker_password
