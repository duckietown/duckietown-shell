import glob
import os
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, Type, Union

from .. import dtslogger
from ..config import remoteurl_from_RepoInfo, RepoInfo, get_config_path
from ..constants import DTShellConstants
from ..environments import ShellCommandEnvironmentAbs, Python3Environment
from ..exceptions import UserError
from ..update_utils import update_cached_commands
from ..utils import run_cmd, undo_replace_spaces


class DTCommandAbs(metaclass=ABCMeta):
    name = None
    level = None
    help = None
    commands = None
    fake = False

    @staticmethod
    @abstractmethod
    def command(shell, args):
        pass

    @staticmethod
    def complete(shell, word, line):
        return []

    @staticmethod
    def fail(msg):
        raise Exception(msg)

    @staticmethod
    def do_command(cls, shell, line):
        # print('>[%s]@(%s, %s)' % (line, cls.name, cls.__class__))
        line = line.strip()
        parts = [p.strip() for p in line.split(" ")]
        args = [p for p in parts if len(p) > 0]

        args = list(map(undo_replace_spaces, args))
        word = parts[0]
        # print('[%s, %r]@(%s, %s)' % (word, parts, cls.name, cls.__class__))
        if len(word) > 0:
            if len(cls.commands) > 0:
                if word in cls.commands:
                    cls.commands[word].do_command(cls.commands[word], shell, " ".join(parts[1:]))
                else:
                    print(
                        "Command `%s` not recognized.\nAvailable sub-commands are:\n\n\t%s"
                        % (word.strip(), "\n\t".join(cls.commands.keys()))
                    )
            else:
                cls.command(shell, args)
        else:
            if len(cls.commands) > 0:
                print("Available sub-commands are:\n\n\t%s" % "\n\t".join(cls.commands.keys()))
            else:
                if not cls.fake:
                    cls.command(shell, args)

    @staticmethod
    def complete_command(cls, shell, word, line, start_index, end_index):
        # print('[%s](%s)@(%s, %s)' % (word, line, cls.name, cls.__class__))
        word = word.strip()
        line = line.strip()
        subcmds = cls.commands.keys()
        parts = [p.strip() for p in line.split(" ")]
        #
        partial_word = len(word) != 0
        if parts[0] == cls.name:
            if len(parts) == 1 or (len(parts) == 2 and partial_word):
                static_comp = [
                    k for k in cls.complete(shell, word, line) if (not partial_word or k.startswith(word))
                ]
                comp_subcmds = static_comp + [k for k in subcmds if (not partial_word or k.startswith(word))]
                # print '!T'
                return comp_subcmds
            if len(parts) > 1 and parts[1] in cls.commands.keys():
                child = parts[1]
                nline = " ".join(parts[1:])
                # print '!C'
                return DTCommandAbs.complete_command(
                    cls.commands[child], shell, word, nline, start_index, end_index
                )
        # print '!D'
        return []

    @staticmethod
    def help_command(cls, shell):
        msg = cls.help if (cls.level == 0 and cls.help is not None) else str(shell.nohelp % cls.name)
        print(msg)


class DTCommandPlaceholder(DTCommandAbs):
    fake = True

    @staticmethod
    def command(shell, args):
        return


@dataclass
class CommandsInfo:
    commands_path: str  # commands path
    leave_alone: bool  # whether to leave this alone (local)


@dataclass
class CommandSetConfiguration:
    default_environment: ShellCommandEnvironmentAbs   # environment in which the commands will run


class DTCommandConfigurationAbs:
    environment: ShellCommandEnvironmentAbs   # environment in which this command will run


class DTCommandConfigurationDefault(DTCommandConfigurationAbs):
    # TODO: we need a way to connect the default environment given by the commandset here
    environment: ShellCommandEnvironmentAbs = Python3Environment()


@dataclass
class CommandDescriptor:
    name: str
    path: str
    selector: str
    configuration: Type[DTCommandConfigurationAbs]
    command: Type[DTCommandAbs] = None
    installed: bool = True


class NoOpCommand(DTCommandAbs):
    @staticmethod
    def command(shell, args, **kwargs):
        pass


class FailedToLoadCommand(NoOpCommand):
    @staticmethod
    def command(shell, args, **kwargs):
        dtslogger.warning("This command was not loaded")


noop_command = SimpleNamespace(DTCommand=NoOpCommand)
failed_to_load_command = SimpleNamespace(DTCommand=FailedToLoadCommand)
default_command_configuration = SimpleNamespace(DTCommandConfiguration=DTCommandConfigurationDefault)


def get_local_commands_info() -> CommandsInfo:
    # define commands_path
    V = DTShellConstants.ENV_COMMANDS
    if V in os.environ:
        commands_path = os.environ[V]

        if not os.path.exists(commands_path):
            msg = "The path %s that you gave with the env. variable %s does not exist." % (commands_path, V)
            raise Exception(msg)

        msg = "Using path %r as prescribed by env variable %s." % (commands_path, V)
        dtslogger.info(msg)
        return CommandsInfo(commands_path, True)
    else:
        commands_path = os.path.join(get_config_path(), "commands")
        return CommandsInfo(commands_path, False)


def init_commands(commands_path: str, repo_info: RepoInfo) -> bool:
    """Raises InvalidRemote if it cannot find it"""
    remote_url = remoteurl_from_RepoInfo(repo_info)
    try:
        dtslogger.info("Downloading Duckietown shell commands in %s ..." % commands_path)
        # clone the repo
        run_cmd(["git", "clone", "-b", repo_info.branch, "--recurse-submodules", remote_url, commands_path])
    except Exception as e:
        # Excepts as InvalidRemote
        dtslogger.error(f"Unable to clone the repo at '{remote_url}'. {str(e)}.")
        return False


def ensure_commands_exist(commands_path: str, repo_info: RepoInfo):
    # clone the commands if necessary
    if not os.path.exists(commands_path):
        init_commands(commands_path, repo_info)
    # make sure the commands exist
    if not os.path.exists(commands_path):
        raise UserError(f"Commands not found at '{commands_path}'.")


def ensure_commands_updated(commands_path: str, repo_info: RepoInfo) -> bool:
    return update_cached_commands(commands_path, repo_info)


def get_commands(path: str, lvl=0, all_commands=False, selector: str = "") \
        -> Union[None, Dict[str, object], CommandDescriptor]:
    entries = glob.glob(os.path.join(path, "*"))
    files = [os.path.basename(e) for e in entries if os.path.isfile(e)]
    dirs = [e for e in entries if os.path.isdir(e) and (lvl > 0 or os.path.basename(e) != "lib")]
    # base case: empty dir -> not a command
    if "command.py" not in files and not dirs:
        return None
    # commands that are not installed
    installed: bool = lvl != 1 or ("installed.flag" in files or "installed.user.flag" in files)
    if not installed and not all_commands:
        return None
    name: str = os.path.basename(path)
    # load subcommands
    subcmds = {}
    for d in dirs:
        cmd_name: str = os.path.basename(d)
        cmd_package = f"{selector}.{cmd_name}".lstrip(".")
        f = get_commands(d, lvl + 1, all_commands, cmd_package)
        if f is not None:
            subcmds[cmd_name] = f
    # not an empty directory, but not a command and not a container of subcommands either
    if "command.py" not in files and not subcmds:
        return None
    # leaf command
    if "command.py" in files and not subcmds:
        return CommandDescriptor(
            name=name,
            path=path,
            selector=selector,
            installed=installed,
            configuration=DTCommandConfigurationDefault
        )
    # ---
    return subcmds
