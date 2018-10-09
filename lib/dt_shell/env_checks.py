import getpass
import subprocess
import sys

from whichcraft import which

from .constants import DTShellConstants


class InvalidEnvironment(Exception):
    pass


def check_docker_environment():
    from . import dtslogger
    dtslogger.debug('checking docker environment')
    check_executable_exists('docker')

    if on_linux():
        username = getpass.getuser()
        if username != 'root':
            check_user_in_group('docker')
        # print('checked groups')
    else:
        pass
        dtslogger.debug('skipping env check because not on Linux')

    try:
        import docker
    except Exception as e:
        msg = 'Could not import package docker:\n%s' % e
        msg += '\n\nTry    pip install --user -U docker'
        raise InvalidEnvironment(msg)

    try:
        client = docker.from_env()
        containers = client.containers.list(filters=dict(status='running'))
    except Exception as e:
        msg = 'I cannot communicate with Docker:\n%s' % e
        msg += '\n\nMake sure the docker service is running.'
        raise InvalidEnvironment(msg)


def on_linux():
    return sys.platform.startswith('linux')


def check_executable_exists(cmdname):
    p = which(cmdname)
    if p is None:
        msg = 'Could not find executable "%s".' % cmdname
        raise InvalidEnvironment(msg)


def check_user_in_group(name):
    active_groups = get_active_groups(username=None)

    if name not in active_groups:
        msg = 'The user is not in group "%s".' % name
        msg += '\n\nIt belongs to groups: %s.' % ", ".join(sorted(active_groups))

        msg += '\n\nNote that when you add a user to a group, you need to login in and out.'
        raise InvalidEnvironment(msg)


def check_git_supports_superproject():
    pass
    #
    # res = system_cmd_result('.', ['git', '--version'],
    #                         display_stdout=False,
    #                         display_stderr=False,
    #                         raise_on_error=True,
    #                         capture_keyboard_interrupt=False,
    #                         env=None)


def get_active_groups(username=None):
    cmd = ['groups']

    if username:
        cmd.append(username)

    try:
        stdout = subprocess.check_output(['groups'])
        # res = system_cmd_result('.', cmd,
        #                         display_stdout=False,
        #                         display_stderr=False,
        #                         raise_on_error=True,
        #                         capture_keyboard_interrupt=False,
        #                         env=None)
    except subprocess.CalledProcessError as e:
        raise Exception(str(e))
    active_groups = stdout.split()
    return active_groups


def get_dockerhub_username(shell=None):
    if shell is None:
        from .cli import DTShell
        shell = DTShell()
    k = DTShellConstants.CONFIG_DOCKER_USERNAME
    if k not in shell.config:
        msg = 'Please set docker username using\n\n dts challenges config --docker-username <USERNAME>'
        raise Exception(msg)

    username = shell.config[k]
    return username
