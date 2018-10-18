# -*- coding: utf-8 -*-
from __future__ import print_function

import glob
import json
import os
import sys
import time
from cmd import Cmd
from os import makedirs, remove, utime
from os.path import basename, isfile, isdir, exists, join, getmtime

import termcolor
from git import Repo
from git.exc import NoSuchPathError, InvalidGitRepositoryError

from . import __version__, dtslogger
from .constants import DTShellConstants
from .dt_command_abs import DTCommandAbs
from .dt_command_placeholder import DTCommandPlaceholder
from .version_check import check_if_outdated

DEBUG = False


class InvalidConfig(Exception):
    pass


CHECK_CMDS_UPDATE_EVERY_MINS = 5

DNAME = 'Duckietown Shell'

INTRO = """

Welcome to the {Duckietown} ({version}).

Type "help" or "?" to list commands.

""".format(Duckietown=termcolor.colored(DNAME, "yellow", attrs=['bold']),
           version=__version__).lstrip()


class DTShell(Cmd, object):
    errors_loading = []
    prompt = 'dt> '
    config = {}
    commands = {}
    core_commands = ['commands', 'install', 'uninstall', 'update', 'version', 'exit', 'help']

    def __init__(self):

        self.intro = INTRO

        # dtslogger.debug('sys.argv: %s' % sys.argv)
        is_shell_outdated = check_if_outdated()

        self.config_path = os.path.expanduser(DTShellConstants.ROOT)
        self.config_file = join(self.config_path, 'config')
        # define commands_path
        V = DTShellConstants.ENV_COMMANDS
        if V in os.environ:
            self.commands_path = os.environ[V]

            if not os.path.exists(self.commands_path):
                msg = 'The path %s that you gave with the env. variable %s does not exist.' % (self.commands_path, V)
                raise Exception(msg)

            self.commands_path_leave_alone = True
            msg = 'Using path %r as prescribed by env variable %s.' % (self.commands_path, V)
            dtslogger.info(msg)
        else:
            self.commands_path = join(self.config_path, 'commands')
            self.commands_path_leave_alone = False
        self.commands_update_check_flag = join(self.commands_path, '.updates-check')
        # add commands_path to the path of this session
        sys.path.insert(0, self.commands_path)
        # add third-party libraries dir to the path of this session
        sys.path.insert(0, join(self.commands_path, 'lib'))

        # create config if it does not exist
        if not exists(self.config_path):
            makedirs(self.config_path)
        if not exists(self.config_file):
            self.save_config()
        # load config
        self.load_config()
        # init commands
        cmds_just_initialized = False
        if exists(self.commands_path) and isfile(self.commands_path):
            remove(self.commands_path)
        if not exists(self.commands_path):
            msg = 'I cannot find the command path %s' % self.commands_path
            dtslogger.warning(msg)
            if not self._init_commands():
                msg = 'I could not initialize the commands.'
                raise Exception(msg)
            cmds_just_initialized = True
        # call super constructor
        super(DTShell, self).__init__()
        # remove the char `-` from the list of word separators, this allows us to suggest flags
        if self.use_rawinput and self.completekey:
            import readline
            readline.set_completer_delims(readline.get_completer_delims().replace('-', '', 1))
        # check for updates (if needed)
        # Do not check it if we are using custom commands_path_leave_alone
        if not is_shell_outdated \
                and not cmds_just_initialized \
                and not self.commands_path_leave_alone \
                and not 'update' in sys.argv:
            self.check_commands_outdated()

        self.reload_commands()

    def postcmd(self, stop, line):
        if len(line.strip()) > 0:
            print('')

    def emptyline(self):
        pass

    def complete(self, text, state):
        res = super(DTShell, self).complete(text, state)
        if res is not None:
            res += ' '
        return res

    def load_config(self):
        with open(self.config_file, 'r') as fp:
            self.config = json.load(fp)

    def save_config(self):
        with open(self.config_file, 'w') as fp:
            json.dump(self.config, fp)

    def check_commands_outdated(self):
        # get local SHA
        try:
            commands_repo = Repo(self.commands_path)
        except (NoSuchPathError, InvalidGitRepositoryError) as e:
            # the repo does not exist, this should never happen
            dtslogger.error('I cannot read the commands repo: %s' % e)
            return
        local_sha = commands_repo.heads.master.commit.hexsha
        # get remote SHA
        use_cached_sha = False
        if exists(self.commands_update_check_flag) and isfile(self.commands_update_check_flag):
            now = time.time()
            last_time_checked = getmtime(self.commands_update_check_flag)
            use_cached_sha = now - last_time_checked < CHECK_CMDS_UPDATE_EVERY_MINS * 60
        # get remote SHA
        if use_cached_sha:
            # no need to check now
            with open(self.commands_update_check_flag, 'r') as fp:
                try:
                    cached_check = json.load(fp)
                except ValueError:
                    return False
                remote_sha = cached_check['remote']
        else:
            url = "https://api.github.com/repos/%s/%s/branches/%s" % (
                DTShellConstants.COMMANDS_REPO_OWNER,
                DTShellConstants.COMMANDS_REPO_NAME,
                DTShellConstants.COMMANDS_REPO_BRANCH
            )
            try:
                from six.moves import urllib
                req = urllib.Request(url)
                res = urllib.urlopen(req, timeout=3)
                content = res.read()
                data = json.loads(content)
                remote_sha = data['commit']['sha']
            except Exception as e:
                return False
        # check if we need to update
        need_update = local_sha != remote_sha
        if need_update:
            msg = """ 
                  
An updated version of the commands is available.

Attempting auto-update.

            """
            self.sprint(msg, color="yellow", attrs=['bold'])

            try:
                self.update_commands()

                # cache remote SHA
                if not use_cached_sha:
                    with open(self.commands_update_check_flag, 'w') as fp:
                        json.dump({'remote': remote_sha}, fp)

            except BaseException as e:
                from .utils import format_exception
                dtslogger.error(format_exception(e))

        # return success
        return True

    def reload_commands(self):
        # get installed commands
        installed_commands = self.commands.keys()
        for command in installed_commands:
            for a in ['do_', 'complete_', 'help_']:
                if hasattr(DTShell, a + command):
                    delattr(DTShell, a + command)
        # re-install commands
        self.commands = self._get_commands(self.commands_path)
        if self.commands is None:
            dtslogger.error('No commands found.')
            self.commands = {}
        # load commands
        # print('commands: %s' % self.commands)
        for cmd, subcmds in self.commands.items():
            self._load_commands('', cmd, subcmds, 0)

        # For Andrea D. : how about this?
        # Commands come in their packages, which allows dependencies.
        # This also allows to give people permission to update only
        # part of the commands.
        try:
            import duckietown_challenges_commands
        except BaseException as e:
            msg = 'Could not import duckietown_challenges_commands: %s' % e
            # print(msg)
        else:
            dirname = os.path.dirname(duckietown_challenges_commands.__file__)
            msg = 'Challenges installed in %s' % dirname
            # print(msg)
            commands = os.path.join(dirname, 'commands')
            if os.path.exists(commands):
                msg = 'Available commands at %s' % commands
                # print(msg)

            # TODO: load commands with prefix "challenges"

        if DTShell.errors_loading:
            msg = """


            !   Could not load commands.

                %s

            !   To recover, you might want to delete the directory
            !
            !      ~/.dt-shell/commands
            !
            !    

            """ % "\n\n".join(DTShell.errors_loading)

            time.sleep(1)
            dtslogger.error(msg)
            time.sleep(5)

    def enable_command(self, command_name):
        if command_name in self.core_commands:
            return True
        # get list of all commands
        res = self._get_commands(self.commands_path, all_commands=True)
        present = res.keys() if res is not None else []
        # enable if possible
        if command_name in present:
            flag_file = join(self.commands_path, command_name, 'installed.user.flag')
            _touch(flag_file)
        return True

    def disable_command(self, command_name):
        if command_name in self.core_commands:
            return False
        # get list of all commands
        res = self._get_commands(self.commands_path, all_commands=True)
        present = res.keys() if res is not None else []
        # enable if possible
        if command_name in present:
            flag_file = join(self.commands_path, command_name, 'installed.user.flag')
            remove(flag_file)
        return True

    def _init_commands(self):
        if self.commands_path_leave_alone:
            msg = 'Will not try to update the commands path.'
            print(msg)
            return True
        self.sprint('Downloading commands in %s ...' % self.commands_path)
        # create commands repo
        commands_repo = Repo.init(self.commands_path)
        # the repo now exists
        origin = commands_repo.create_remote('origin', DTShellConstants.COMMANDS_REMOTE_URL)
        # check existence of `origin`
        if not origin.exists():
            dtslogger.error('The commands repository %r cannot be found. Exiting.' % origin.urls)
            return False
        # pull data
        origin.fetch()
        # create local.master <-> remote.master
        commands_repo.create_head('master', origin.refs.master)
        commands_repo.heads.master.set_tracking_branch(origin.refs.master)
        # pull data
        _res = origin.pull()
        # the repo is there and there is a `origin` remote, merge
        commands_repo.heads.master.checkout()
        return True

    def update_commands(self):
        # create commands repo
        commands_repo = None
        try:
            commands_repo = Repo(self.commands_path)
        except (NoSuchPathError, InvalidGitRepositoryError) as e:
            # the repo does not exist
            if not self._init_commands():
                return False
        # the repo exists
        self.sprint('Updating commands...')
        origin = commands_repo.remote('origin')
        # check existence of `origin`
        if not origin.exists():
            dtslogger.error('The commands repository %r cannot be found. Exiting.' % origin.urls)
            return False
        _res = origin.pull()
        # pull data from remote.master to local.master
        commands_repo.heads.master.checkout()

        # # update all submodules
        # print('Updating libraries...', end='')
        # try:
        #     commands_repo.submodule_update(recursive=True, to_latest_revision=False)
        # except Exception as e:
        #     msg = 'Could not update libraries: %s' % e
        #     dtslogger.error(msg)

        # TODO: make sure this is not necessary
        # for submodule in commands_repo.submodules:
        #     submodule.update(recursive=True, to_latest_revision=False)

        # everything should be fine
        self.sprint('OK')
        # cache current (local=remote) SHA
        current_sha = commands_repo.heads.master.commit.hexsha
        with open(self.commands_update_check_flag, 'w') as fp:
            json.dump({'remote': current_sha}, fp)
        # return success
        return True

    def _get_commands(self, path, lvl=0, all_commands=False):
        entries = glob.glob(join(path, '*'))
        files = [basename(e) for e in entries if isfile(e)]
        dirs = [e for e in entries if isdir(e) and (lvl > 0 or basename(e) != 'lib')]
        # base case: empty dir
        if 'command.py' not in files and not dirs:
            return None
        if not all_commands and lvl == 1 and ('installed.flag' not in files and 'installed.user.flag' not in files):
            return None
        # check subcommands
        subcmds = {}
        for d in dirs:
            f = self._get_commands(d, lvl + 1, all_commands)
            if f is not None:
                subcmds[basename(d)] = f
        # return
        return subcmds

    def _load_commands(self, package, command, sub_commands, lvl):
        # load command
        klass = None
        error_loading = False
        if not sub_commands:
            spec = package + command + '.command.DTCommand'
            try:
                klass = _load_class(spec)
            except BaseException as e:
                # error_loading = True
                from .utils import format_exception
                se = format_exception(e)

                msg = 'Cannot load command class %r (package=%r, command=%r): %s' % (
                    spec, package, command, se)
                # msg += ' sys.path: %s' % sys.path
                DTShell.errors_loading.append(msg)
                return

        # handle loading error and wrong class
        if error_loading:
            klass = DTCommandPlaceholder()
            if DEBUG:
                dtslogger.debug('ERROR while loading the command `%s`' % (package + command + '.command.DTCommand',))
        if not issubclass(klass.__class__, DTCommandAbs.__class__):
            klass = DTCommandPlaceholder()
            if DEBUG:
                dtslogger.debug('Command `%s` not found' % (package + command + '.command.DTCommand',))
        # initialize list of subcommands
        klass.name = command
        klass.level = lvl
        klass.commands = {}
        # attach first-level commands to the shell
        if lvl == 0:
            do_command = getattr(klass, 'do_command')
            complete_command = getattr(klass, 'complete_command')
            help_command = getattr(klass, 'help_command')
            # wrap [klass, function] around a lambda function
            do_command_lam = lambda s, w: do_command(klass, s, w)
            complete_command_lam = lambda s, w, l, i, e: complete_command(klass, s, w, l, i, e)
            help_command_lam = lambda s: help_command(klass, s)
            # add functions do_* and complete_* to the shell
            setattr(DTShell, 'do_' + command, do_command_lam)
            setattr(DTShell, 'complete_' + command, complete_command_lam)
            setattr(DTShell, 'help_' + command, help_command_lam)
        # stop recursion if there is no subcommand
        if sub_commands is None:
            return
        # load sub-commands
        for cmd, subcmds in sub_commands.items():
            if DEBUG:
                dtslogger.debug('DEBUG:: Loading %s' % package + command + '.*')
            kl = self._load_commands(package + command + '.', cmd, subcmds, lvl + 1)
            if kl is not None:
                klass.commands[cmd] = kl
        # return class for this command
        return klass

    def get_dt1_token(self):
        k = DTShellConstants.DT1_TOKEN_CONFIG_KEY
        if k not in self.config:
            msg = 'Please set up a token for this using "dts tok set".'
            raise Exception(msg)

        token = self.config[k]
        return token

    def sprint(self, msg, color=None, attrs=None):
        return dts_print(msg=msg, color=color, attrs=attrs)


def dts_print(msg, color=None, attrs=None):
    '''
        Prints a message to the user.
    '''
    msg = msg.strip()  # remove space
    print('')  # always separate
    lines = msg.split('\n')
    prefix = 'dts : '
    filler = '    : '
    # filler = ' ' * len(prefix)

    for i, line in enumerate(lines):
        f = prefix if i == 0 else filler
        line = termcolor.colored(line, color=color, attrs=attrs)
        s = '%s %s' % (dark_yellow(f), line)
        print(s)


def dark_yellow(x):
    return termcolor.colored(x, 'yellow', attrs=[])


def dark(x):
    return termcolor.colored(x, attrs=['dark'])


def _touch(path):
    with open(path, 'a'):
        utime(path, None)


def _load_class(name):
    if DEBUG:
        print('DEBUG:: Loading %s' % name)
    components = name.split('.')

    mod = __import__(components[0])

    for comp in components[1:]:
        try:
            mod = getattr(mod, comp)
        except AttributeError as e:
            msg = 'Could not get field %r of module %r: %s' % (comp, mod.__name__, e)
            msg += '\n module file %s' % getattr(mod, '__file__', '?')
            raise AttributeError(msg)
    return mod
