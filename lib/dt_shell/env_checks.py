import sys

from system_cmd import system_cmd_result, CmdException
from whichcraft import which


class InvalidEnvironment(Exception):
    pass


def check_docker_environment():
    print('checking docker environment')
    check_executable_exists('docker')

    if on_linux():
        check_user_in_group('docker')
        print('checked groups')
    else:
        print('skipping env check')


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
        msg += '\nIt belongs to groups: %s.' % ", ".join(sorted(active_groups))
        raise InvalidEnvironment(msg)


def get_active_groups(username=None):
    cmd = ['groups']

    if username:
        cmd.append(username)

    try:
        res = system_cmd_result('.', cmd,
                                display_stdout=False,
                                display_stderr=False,
                                raise_on_error=True,
                                capture_keyboard_interrupt=False,
                                env=None)
    except CmdException as e:
        raise Exception(str(e))
    active_groups = res.stdout.split()  # XXX
    return active_groups
