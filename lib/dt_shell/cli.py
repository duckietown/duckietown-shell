# -*- coding: utf-8 -*-
import os
import sys
import time
import types
from cmd import Cmd
from dataclasses import dataclass
from os import remove, utime
from os.path import exists, isfile, join
from typing import Mapping, Optional, Sequence

from . import dtslogger
from .commands_ import (
    _get_commands,
    _init_commands,
    check_commands_outdated,
    InvalidRemote,
    update_commands,
)
from .config import (
    get_config_path,
    RepoInfo,
    RepoInfo_for_version,
    ShellConfig,
    write_shell_config,
)
from .constants import DEBUG, DTShellConstants, INTRO
from .dt_command_abs import DTCommandAbs
from .dt_command_placeholder import DTCommandPlaceholder
from .exceptions import CommandsLoadingException, UserError
from .logging import dts_print
from .version_check import check_if_outdated


@dataclass
class CommandsInfo:
    commands_path: str  # commands path
    leave_alone: bool  # whether to leave this alone (local)


def get_local_commands_info() -> CommandsInfo:
    # define commands_path
    config_path = get_config_path()
    V = DTShellConstants.ENV_COMMANDS
    if V in os.environ:
        commands_path = os.environ[V]

        if not os.path.exists(commands_path):
            msg = "The path %s that you gave with the env. variable %s does not exist." % (commands_path, V)
            raise Exception(msg)

        commands_path_leave_alone = True
        msg = "Using path %r as prescribed by env variable %s." % (commands_path, V)
        dtslogger.info(msg)
    else:
        commands_path = join(config_path, "commands-multi")
        commands_path_leave_alone = False
    return CommandsInfo(commands_path, commands_path_leave_alone)


prompt = "dts> "


class DTShell(Cmd):
    errors_loading = []

    # config = {}
    commands = {}
    core_commands = [
        "commands",
        "install",
        "uninstall",
        "update",
        "version",
        "exit",
        "help",
    ]

    shell_config: ShellConfig
    local_commands_info: CommandsInfo
    repo_info: RepoInfo
    commands_path: str

    include: types.SimpleNamespace

    def __init__(self, shell_config: ShellConfig, commands_info: CommandsInfo):
        self.shell_config = shell_config
        self.local_commands_info = commands_info

        self.intro = INTRO
        setattr(DTShell, "include", types.SimpleNamespace())

        # dtslogger.debug('sys.argv: %s' % sys.argv)
        check_if_outdated()

        self.repo_info = RepoInfo_for_version(shell_config.duckietown_version)
        self.commands_path = commands_path = self.local_commands_info.commands_path

        # add commands_path to the path of this session
        sys.path.insert(0, self.commands_path)
        # add third-party libraries dir to the path of this session
        sys.path.insert(0, os.path.join(self.commands_path, "lib"))

        # init commands
        cmds_just_initialized = False

        if exists(commands_path) and isfile(commands_path):
            remove(commands_path)
        if not exists(commands_path):
            msg = "I cannot find the command path %s" % commands_path
            if self.local_commands_info.leave_alone:
                raise Exception(msg)
            dtslogger.warning(msg)
            try:
                _init_commands(commands_path, self.repo_info)
            except InvalidRemote as e:
                msg = "I could not initialize the commands."
                raise CommandsLoadingException(msg) from e
            cmds_just_initialized = True

        # call super constructor
        super(DTShell, self).__init__()
        # remove the char `-` from the list of word separators, this allows us to suggest flags
        if self.use_rawinput and self.completekey:
            import readline

            readline.set_completer_delims(readline.get_completer_delims().replace("-", "", 1))
        # check for updates (if needed)
        # Do not check it if we are using custom commands_path_leave_alone
        if (
            not cmds_just_initialized
            and not self.local_commands_info.leave_alone
            and not "update" in sys.argv
        ):
            check_commands_outdated(self.commands_path, self.repo_info)

        self.reload_commands()

    def save_config(self):
        write_shell_config(self.shell_config)

    def postcmd(self, stop, line):
        if len(line.strip()) > 0:
            print("")

    def emptyline(self):
        pass

    def complete(self, text, state):
        res = super(DTShell, self).complete(text, state)
        if res is not None:
            res += " "
        return res

    def reload_commands(self):
        # get installed commands
        installed_commands = self.commands.keys()
        for command in installed_commands:
            for a in ["do_", "complete_", "help_"]:
                if hasattr(DTShell, a + command):
                    delattr(DTShell, a + command)
        # re-install commands
        self.commands = _get_commands(self.commands_path)
        if self.commands is None:
            dtslogger.error("No commands found.")
            self.commands = {}
        # load commands
        # print('commands: %s' % self.commands)
        for cmd, subcmds in self.commands.items():
            # noinspection PyTypeChecker
            self._load_commands("", cmd, subcmds, 0)

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

            """ % "\n\n".join(
                DTShell.errors_loading
            )

            time.sleep(1)
            dtslogger.error(msg)
            time.sleep(5)

    def enable_command(self, command_name):
        if command_name in self.core_commands:
            return True
        # get list of all commands
        res = _get_commands(self.commands_path, all_commands=True)
        present = res.keys() if res is not None else []
        # enable if possible
        if command_name in present:
            flag_file = join(self.commands_path, command_name, "installed.user.flag")
            _touch(flag_file)
        return True

    def disable_command(self, command_name):
        if command_name in self.core_commands:
            return False
        # get list of all commands
        res = _get_commands(self.commands_path, all_commands=True)
        present = res.keys() if res is not None else []
        # enable if possible
        if command_name in present:
            flag_file = join(self.commands_path, command_name, "installed.user.flag")
            remove(flag_file)
        return True

    def _load_commands(self, package, command, sub_commands: Optional[Mapping[str, object]], lvl):
        # load command
        klass = None
        error_loading = False
        if not sub_commands:
            spec = package + command + ".command.DTCommand"
            try:
                klass = _load_class(spec)
                # add loaded class to DTShell.include.<cmd_path>
                klass_path = [p for p in package.split(".") if len(p)]
                base = DTShell.include
                for p in klass_path:
                    if not hasattr(base, p):
                        setattr(base, p, types.SimpleNamespace())
                    base = getattr(base, p)
                setattr(base, command, klass)
            except UserError:
                raise
            except KeyboardInterrupt:
                raise
            except BaseException as e:
                # error_loading = True
                from .utils import format_exception

                se = format_exception(e)

                msg = "Cannot load command class %r (package=%r, command=%r): %s" % (
                    spec,
                    package,
                    command,
                    se,
                )
                # msg += ' sys.path: %s' % sys.path
                DTShell.errors_loading.append(msg)
                return

        # handle loading error and wrong class
        if error_loading:
            klass = DTCommandPlaceholder()
            if DEBUG:
                dtslogger.debug(
                    "ERROR while loading the command `%s`" % (package + command + ".command.DTCommand",)
                )
        if not issubclass(klass.__class__, DTCommandAbs.__class__):
            klass = DTCommandPlaceholder()
            if DEBUG:
                dtslogger.debug("Command `%s` not found" % (package + command + ".command.DTCommand",))
        # initialize list of subcommands
        klass.name = command
        klass.level = lvl
        klass.commands = {}
        # attach first-level commands to the shell
        if lvl == 0:
            do_command = getattr(klass, "do_command")
            complete_command = getattr(klass, "complete_command")
            help_command = getattr(klass, "help_command")
            # wrap [klass, function] around a lambda function
            do_command_lam = lambda s, w: do_command(klass, s, w)
            complete_command_lam = lambda s, w, l, i, _: complete_command(klass, s, w, l, i, _)
            help_command_lam = lambda s: help_command(klass, s)
            # add functions do_* and complete_* to the shell
            setattr(DTShell, "do_" + command, do_command_lam)
            setattr(DTShell, "complete_" + command, complete_command_lam)
            setattr(DTShell, "help_" + command, help_command_lam)

        # stop recursion if there is no subcommand
        if sub_commands is None:
            return
        # load sub-commands
        for cmd, subcmds in sub_commands.items():
            if DEBUG:
                dtslogger.debug("Searching %s at level %d" % (package + command + ".*", lvl))
            # noinspection PyTypeChecker
            kl = self._load_commands(package + command + ".", cmd, subcmds, lvl + 1)
            if kl is not None:
                klass.commands[cmd] = kl
        # return class for this command
        return klass

    def get_dt1_token(self) -> str:
        var = DTShellConstants.DT1_TOKEN_CONFIG_KEY
        from_env = os.environ.get(var, None)
        if from_env:
            msg = f"Using token from environment variable {var} instead of config."
            dtslogger.info(msg)
            return from_env

        if self.shell_config.token_dt1 is None:
            msg = 'Please set up a token for this using "dts tok set".'
            raise Exception(msg)
        else:
            return self.shell_config.token_dt1

    def get_commands_version(self) -> str:
        return self.shell_config.duckietown_version

    # noinspection PyMethodMayBeStatic
    def sprint(self, msg: str, color: Optional[str] = None, attrs: Sequence[str] = None) -> None:
        attrs = attrs or []
        return dts_print(msg=msg, color=color, attrs=attrs)

    def update_commands(self) -> bool:
        return update_commands(self.commands_path, self.repo_info)


def _touch(path: str) -> None:
    with open(path, "a"):
        utime(path, None)


def _load_class(name):
    if DEBUG:
        dtslogger.debug("Loading class %s" % name)
    components = name.split(".")

    mod = __import__(components[0])

    for comp in components[1:]:
        try:
            mod = getattr(mod, comp)
        except AttributeError as e:
            msg = "Could not get field %r of module %r: %s" % (comp, mod.__name__, e)
            msg += "\t\n - Module file %s;" % getattr(mod, "__file__", "?")
            msg += "\t\n - Module content %s;" % list(vars(mod).keys())
            raise AttributeError(msg)
    return mod
