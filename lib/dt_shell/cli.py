# -*- coding: utf-8 -*-
import argparse
import os
import random
import sys
import time
import traceback
import types
from cmd import Cmd
from dataclasses import dataclass
from os import remove, utime
from os.path import exists, isfile, join
from typing import List, Optional, Tuple, Union, Type
from typing import Mapping, Sequence

from dt_shell.user_profile import UserProfile

from dt_shell.database.database import DTShellDatabase

from . import dtslogger
from .checks.version import check_if_outdated
from .commands import \
    DTCommandAbs, \
    CommandsInfo, \
    CommandDescriptor, \
    DTCommandPlaceholder, \
    get_commands, \
    init_commands, \
    ensure_commands_exist, \
    ensure_commands_updated, \
    DTCommandConfigurationAbs
from .commands.importer import import_command, import_configuration
from .config import (
    RepoInfo,
    RepoInfo_for_version,
    ShellConfig,
    write_shell_config,
)
from .constants import ALLOWED_BRANCHES, DEFAULT_PROFILE
from .constants import DEBUG, DTShellConstants, INTRO
from .environments import Python3Environment
from .exceptions import CommandsLoadingException, UserError, InvalidRemote
from .logging import dts_print

BILLBOARDS_VERSION: str = "v1"


@dataclass
class CLIOptions:
    debug: bool
    set_version: Optional[str]
    quiet: bool


def get_cli_options(args: List[str]) -> Tuple[CLIOptions, List[str]]:
    """Returns cli options plus other arguments for the commands."""
    allowed_branches = [b.split("(")[0] for b in ALLOWED_BRANCHES]

    if args and not args[0].startswith("-"):
        return CLIOptions(debug=False, set_version=None, quiet=False), args
    parser = argparse.ArgumentParser()

    parser.add_argument("--debug", action="store_true", default=False, help="More debug information")
    parser.add_argument("-q", "--quiet", action="store_true", default=False, help="Quiet execution")
    parser.add_argument(
        "--set-version",
        type=str,
        default=None,
        help=f"Set Duckietown version. Use one of {allowed_branches}. Branches from "
             f"https://github.com/duckietown/duckietown-shell-commands of the form '[branch]-*' are also "
             f"supported.",
    )

    parsed, others = parser.parse_known_args(args)

    return CLIOptions(debug=parsed.debug, set_version=parsed.set_version, quiet=parsed.quiet), others


prompt = "dts> "


class DTShell(Cmd):
    errors_loading = []

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

    # TODO: this needs to go in favor of Databases
    shell_config: ShellConfig

    # TODO: these need to go and have a similar functionality in the profile
    local_commands_info: CommandsInfo
    repo_info: RepoInfo
    commands_path: str

    # tree of commands once loaded
    include: types.SimpleNamespace

    def __init__(self, shell_config: ShellConfig, commands_info: CommandsInfo):
        self.shell_config = shell_config
        self.local_commands_info = commands_info

        self.intro = INTRO()
        setattr(DTShell, "include", types.SimpleNamespace())

        # open databases
        self._db_profiles: DTShellDatabase = DTShellDatabase.open("profiles")
        self._db_settings: DTShellDatabase = DTShellDatabase.open("settings")
        self._db_user: DTShellDatabase = DTShellDatabase.open("user")

        # load current profile
        self._current_profile_name: str = self._db_user.get("active_profile", DEFAULT_PROFILE)
        self._current_profile: UserProfile = UserProfile(self._current_profile_name)

        # update shell constants
        DTShellConstants.PROFILE = self._current_profile
        DTShellConstants.ROOT = self._current_profile.path

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

        # check if the commands path exists
        if exists(commands_path) and isfile(commands_path):
            remove(commands_path)
        if not exists(commands_path):
            msg = "I cannot find the command path %s" % commands_path
            if self.local_commands_info.leave_alone:
                raise Exception(msg)
            dtslogger.warning(msg)
            try:
                init_commands(commands_path, self.repo_info)
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
            and "update" not in sys.argv
        ):
            self.update_commands()

        # show billboard (if any)
        billboard: Optional[str] = self.get_billboard()
        if billboard:
            print(billboard)

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
        self.commands = get_commands(self.commands_path)
        if self.commands is None:
            dtslogger.error("No commands found.")
            self.commands = {}
        # load commands
        for cmd, subcmds in self.commands.items():
            # noinspection PyTypeChecker
            self._load_commands("", cmd, subcmds, 0)

        # TODO: load commands with prefix "challenges"

        if DTShell.errors_loading:
            msg = f"""


            !   Could not load commands.

                %s

            !   To recover, you might want to delete the following profile directory
            !
            !      {DTShellConstants.ROOT}
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
        res = get_commands(self.commands_path, all_commands=True)
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
        res = get_commands(self.commands_path, all_commands=True)
        present = res.keys() if res is not None else []
        # enable if possible
        if command_name in present:
            flag_file = join(self.commands_path, command_name, "installed.user.flag")
            remove(flag_file)
        return True

    def _load_commands(self,
                       package: str,
                       command: str,
                       sub_commands: Union[None, Mapping[str, object], CommandDescriptor],
                       lvl: int) -> Union[None, Type[DTCommandAbs]]:
        # print("package: ", package, "command: ", command, "sub_commands: ", sub_commands, "lvl: ", lvl)
        # load command
        klass = DTCommandPlaceholder()
        if isinstance(sub_commands, CommandDescriptor):
            descriptor: CommandDescriptor = sub_commands
            # load command configuration
            configuration: Type[DTCommandConfigurationAbs] = import_configuration(descriptor.path)
            descriptor.configuration = configuration
            # import class only if this is the environment in which the commands will run
            if isinstance(descriptor.configuration.environment, Python3Environment):
                try:
                    klass = import_command(descriptor.configuration, descriptor.path)
                    descriptor.command = klass
                except UserError:
                    raise
                except KeyboardInterrupt:
                    raise
                except BaseException:
                    se = traceback.format_exc()
                    msg = f"Cannot load command class {descriptor.selector}.command.DTCommand " \
                          f"(package={package}, command={command}): {se}"
                    DTShell.errors_loading.append(msg)
                    return

            descriptor.command = klass
            # add loaded class to DTShell.include.<cmd_path>
            klass_path = [p for p in package.split(".") if len(p)]
            base = DTShell.include
            for p in klass_path:
                if not hasattr(base, p):
                    setattr(base, p, types.SimpleNamespace())
                base = getattr(base, p)
            setattr(base, command, klass)

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
        if isinstance(sub_commands, dict):
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

    @staticmethod
    def get_billboard() -> Optional[str]:
        # find billboards directory
        dts_dir: str = os.path.expanduser(DTShellConstants.ROOT)
        billboard_dir: str = os.path.join(dts_dir, "billboards", BILLBOARDS_VERSION)
        if (not os.path.exists(billboard_dir)) or (not os.path.isdir(billboard_dir)):
            return None
        # get all sources of ads from the billboards directory
        sources: List[str] = os.listdir(billboard_dir)
        if len(sources) <= 0:
            return None
        # pick one source at random
        source: str = random.choice(sources)
        try:
            with open(os.path.join(billboard_dir, source), "rt") as fin:
                content: str = fin.read()
        except:
            dtslogger.debug("Error occurred while loading billboard. Skipping...")
            return None
        # ---
        return content

    def update_commands(self) -> bool:
        # check that the repo is initialized in the commands path
        ensure_commands_exist(self.commands_path, self.repo_info)
        # update the commands if they are outdated
        return ensure_commands_updated(self.commands_path, self.repo_info)


def _touch(path: str) -> None:
    with open(path, "a"):
        utime(path, None)
