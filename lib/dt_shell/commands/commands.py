import argparse
import copy
import dataclasses
import glob
import inspect
import os
import time
import traceback
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, Type, Union, Optional, Mapping, Tuple, List, Any

from .repository import CommandsRepository
from .. import __version__, logger
from ..constants import CHECK_CMDS_UPDATE_MINS, DB_COMMAND_SET_UPDATES_CHECK, DTShellConstants, \
    EMBEDDED_COMMAND_SET_NAME
from ..environments import ShellCommandEnvironmentAbs, Python3Environment
from ..exceptions import UserError, InvalidRemote, CommandsLoadingException, CommandNotFound
from ..utils import run_cmd, undo_replace_spaces


CommandName = str
CommandsTree = Dict[CommandName, Union[Mapping[CommandName, dict], Type['DTCommandAbs']]]


class DTCommandAbs(metaclass=ABCMeta):
    name: str = None
    level: int = None
    help: str = None
    commands: CommandsTree = None
    descriptor: 'CommandDescriptor' = None
    fake: bool = False

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

    @classmethod
    def aliases(cls) -> List[str]:
        if not cls.descriptor:
            return []
        if not cls.descriptor.configuration:
            return []
        return cls.descriptor.configuration.aliases()

    @staticmethod
    def get_command(cls, shell, line) -> Tuple['CommandDescriptor', List[str]]:
        cls: Type[DTCommandAbs]
        line: str
        # ---
        # print('>[%s]@(%s, %s)' % (line, cls.name, cls.__class__))
        line = line.strip()
        parts = [p.strip() for p in line.split(" ")]
        args = [p for p in parts if len(p) > 0]
        args = list(map(undo_replace_spaces, args))
        word = parts[0]
        # print('[%s, %r]@(%s, %s)' % (word, parts, cls.name, cls.__class__))
        if len(word) > 0:
            if len(cls.commands) > 0:
                # search every command and their aliases
                subcmds: Dict[str, Type[DTCommandAbs]] = copy.copy(cls.commands)
                for subcmd_name, subcmd in cls.commands.items():
                    subcmds.update({k: subcmd for k in subcmd.aliases()})
                # if we have a match we keep looking down recursively
                if word in subcmds:
                    return subcmds[word].get_command(subcmds[word], shell, " ".join(parts[1:]))
                else:
                    raise CommandNotFound(last_matched=cls, remaining=parts)
            else:
                return cls.descriptor, args
        else:
            if len(cls.commands) > 0:
                raise CommandNotFound(last_matched=cls, remaining=parts)
            else:
                return cls.descriptor, args

    @staticmethod
    def do_command(cls, shell, line):
        cls: Type[DTCommandAbs]
        line: str
        # ---
        descriptor: Optional[CommandDescriptor]
        args: List[str]
        # find the subcommand to execute
        descriptor, args = DTCommandAbs.get_command(cls, shell, line)
        if descriptor is not None and not descriptor.command.fake:
            # run command implementation
            return descriptor.command.command(shell, args)

    @staticmethod
    def complete_command(cls, shell, word, line, start_index, end_index):
        cls: Type[DTCommandAbs]
        word: str
        line: str
        start_index: int
        end_index: int
        # ---
        # print('[%s](%s)@(%s, %s)' % (word, line, cls.name, cls.__class__))
        word = word.strip()
        line = line.strip()
        # add aliases
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
        # ---
        return []

    @staticmethod
    def help_command(cls, shell):
        cls: Type[DTCommandAbs]
        # ---
        msg = cls.help if (cls.level == 0 and cls.help is not None) else str(shell.nohelp % cls.name)
        print(msg)


class DTCommandPlaceholder(DTCommandAbs):
    fake = True

    @staticmethod
    def command(shell, args):
        return


class NoOpCommand(DTCommandAbs):
    @staticmethod
    def command(shell, args, **kwargs):
        pass


class FailedToLoadCommand(NoOpCommand):
    @staticmethod
    def command(shell, args, **kwargs):
        logger.warning("This command was not loaded")


class DTCommandConfigurationAbs(metaclass=ABCMeta):

    @classmethod
    def environment(cls, **kwargs) -> Optional[ShellCommandEnvironmentAbs]:
        """
        The environment in which this command will run.
        """
        return None

    @classmethod
    def parser(cls, **kwargs) -> Optional[argparse.ArgumentParser]:
        """
        The parser this command will use.
        """
        return None

    @classmethod
    def aliases(cls) -> List[str]:
        """
        Alternative names for this command.
        """
        return []


class DTCommandConfigurationDefault(DTCommandConfigurationAbs):
    pass


class DTCommandSetConfigurationAbs(metaclass=ABCMeta):
    path: str = None

    @classmethod
    def default_environment(cls, **kwargs) -> Optional[ShellCommandEnvironmentAbs]:
        """
        The environment in which the commands in this set will run.
        """
        return None

    @classmethod
    def requirements(cls, **_) -> Optional[str]:
        """
        File containing the list of dependency python projects needed by the commands in this command set.
        """
        # no path => no requirements file
        if cls.path is None:
            return None
        # return the path to the requirements file if it exists
        command_set_metadir: str = os.path.join(os.path.abspath(cls.path), "__command_set__")
        requirements_fpath: str = os.path.join(command_set_metadir, "requirements.txt")
        return requirements_fpath if os.path.exists(requirements_fpath) else None


class DTCommandSetConfigurationDefault(DTCommandSetConfigurationAbs):

    @classmethod
    def default_environment(cls, **kwargs) -> Optional[ShellCommandEnvironmentAbs]:
        """
        The environment in which commands from this command set will run.
        """
        return Python3Environment()


@dataclass
class CommandDescriptor:
    name: str
    path: str
    selector: str
    configuration: Type[DTCommandConfigurationAbs]
    environment: Optional[ShellCommandEnvironmentAbs] = None
    command: Type[DTCommandAbs] = None

    @property
    def aliases(self) -> List[str]:
        return self.configuration.aliases()


noop_command = SimpleNamespace(DTCommand=NoOpCommand)
failed_to_load_command = SimpleNamespace(DTCommand=FailedToLoadCommand)
default_command_configuration = SimpleNamespace(DTCommandConfiguration=DTCommandConfigurationDefault)
default_commandset_configuration = SimpleNamespace(DTCommandSetConfiguration=DTCommandSetConfigurationDefault)


@dataclass
class CommandSet:
    name: str
    path: str
    profile: Any
    repository: Optional[CommandsRepository] = None
    leave_alone: bool = False
    configuration: Type[DTCommandSetConfigurationAbs] = None
    commands: CommandsTree = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        from .importer import import_commandset_configuration
        # load command set configuration
        self.configuration: Type[DTCommandSetConfigurationAbs] = import_commandset_configuration(self)
        # load commands
        self.commands = self._find_commands()

    @property
    def version(self) -> Optional[str]:
        # embedded command set
        if self.name == EMBEDDED_COMMAND_SET_NAME:
            return __version__
        # repository-based command sets
        if self.repository:
            return CommandsRepository.head_tag(self.path)
        # no repository
        return None

    @property
    def closest_version(self) -> Optional[str]:
        # embedded command set
        if self.name == EMBEDDED_COMMAND_SET_NAME:
            return __version__
        # repository-based command sets
        if self.repository:
            return CommandsRepository.closest_tag(self.path)
        # no repository
        return None

    @property
    def local_sha(self) -> Optional[str]:
        if self.repository is not None:
            stdout: str = run_cmd(["git", "-C", self.path, "rev-parse", "HEAD"])
            # noinspection PyTypeChecker
            return next(filter(len, stdout.split("\n")))

    def refresh(self):
        # reload commands
        self.commands = self._find_commands()

    def command_path(self, selector: str) -> str:
        return os.path.join(self.path, selector.strip(".").replace(".", os.path.sep))

    def download(self) -> bool:
        """Raises InvalidRemote if it cannot find it"""
        if self.repository is None:
            raise RuntimeError("You cannot 'download' a command set without a repository defined.")
        # ---
        remote_url = self.repository.remoteurl
        try:
            logger.info(f"Downloading Duckietown shell commands in {self.path} ...")
            # clone the repo
            branch: List[str] = ["--branch", self.repository.branch] if self.repository.branch else []
            run_cmd(["git", "clone"] + branch + ["--recurse-submodules", remote_url, self.path])
            logger.info(f"Commands downloaded successfully!")
            # refresh commands
            self.refresh()
        except Exception as e:
            # Excepts as InvalidRemote
            logger.error(f"Unable to clone the repo at '{remote_url}':\n{str(e)}.")
            return False

    def update(self) -> bool:
        # check that the repo is initialized in the commands path
        self.ensure_commands_exist()
        # update the commands if they are outdated
        return self.ensure_commands_updated()

    def ensure_commands_exist(self):
        # clone the commands if necessary
        if not os.path.exists(self.path):
            msg = f"I cannot find the command path {self.path}"
            if self.leave_alone:
                raise Exception(msg)
            logger.debug(msg)
            # we can download
            try:
                self.download()
            except InvalidRemote as e:
                msg = "I could not initialize the commands."
                raise CommandsLoadingException(msg) from e
        # make sure the commands exist
        if not os.path.exists(self.path):
            raise UserError(f"Commands not found at '{self.path}'.")

    def commands_need_update(self) -> bool:
        # command sets without repository cannot be updated
        if self.repository is None:
            return False
        # ---
        need_update: bool = False
        # get the current repo info
        db = self.profile.database(DB_COMMAND_SET_UPDATES_CHECK)
        # check if it's time to check for an update
        record: dict
        if db.contains(self.name):
            record = db.get(self.name)
            now = time.time()
            last_time_checked = record["time"]
            use_cached_commands = now - last_time_checked < CHECK_CMDS_UPDATE_MINS * 60
        else:
            # save the initial update record
            self.mark_as_just_updated()
            return False

        # check for an updated remote
        if not use_cached_commands:
            logger.info(f"Checking for updates for the command set '{self.name}'...")
            # get the local sha from file
            local_sha: Optional[str] = record["sha"]
            if local_sha is None:
                logger.error(f"Command set '{self.name}' has a repository but no local sha. "
                             f"This should not have happened. Contact technical support.")
                # TODO: maybe corrupted repository? suggest removing and reinstalling the command set?
                return False

            # get the remote sha from GitHub
            remote_sha: Optional[str] = self.repository.remote_sha()
            if remote_sha is None:
                return False

            # check if we need to update
            need_update = local_sha != remote_sha
            # touch flag to reset update check time
            self.mark_as_just_updated()
        # ---
        return need_update

    def mark_as_just_updated(self):
        db = self.profile.database(DB_COMMAND_SET_UPDATES_CHECK)
        db.set(self.name, {"sha": self.local_sha, "time": time.time()})

    def ensure_commands_updated(self) -> bool:
        # make sure the commands directory exists
        if not os.path.exists(self.path) and os.path.isdir(self.path):
            raise RuntimeError(f"There is no existing commands directory in '{self.path}'.")

        # command sets without repository cannot be updated
        if self.repository is None:
            raise RuntimeError("Command sets without a repository defined cannot be updated.")

        # Check for shell commands repo updates
        logger.debug(f"Checking for updates for the command set '{self.name}'...")
        if self.commands_need_update():
            logger.info(f"The command set '{self.name}' has available updates. Attempting to pull them.")
            wait_on_retry_secs = 4
            th = {2: "nd", 3: "rd", 4: "th"}
            for trial in range(3):
                try:
                    run_cmd(["git", "-C", self.path, "pull", "--recurse-submodules", "origin",
                             self.repository.branch])
                    logger.info(f"Command set '{self.name}' successfully updated!")
                except RuntimeError:
                    if DTShellConstants.VERBOSE:
                        traceback.print_exc()
                    logger.warning(
                        f"An error occurred while pulling the updated commands. In {wait_on_retry_secs} "
                        f"seconds we will retry for the {trial + 2}-{th[trial + 2]} time"
                    )
                    time.sleep(wait_on_retry_secs)
                else:
                    break
            run_cmd(["git", "-C", self.path, "submodule", "update"])
            # mark as updated
            self.mark_as_just_updated()
            # refresh commands
            self.refresh()
            # ---
            return True
        else:
            logger.debug(f"Command set '{self.name}' is up-to-date.")
            # ---
            return False

    def _find_commands(self, lvl=0, all_commands=False, selector: str = "", path: Optional[str] = None) \
            -> Union[None, Dict[str, Union[dict, CommandDescriptor]], CommandDescriptor]:
        path: str = path or self.path
        entries = glob.glob(os.path.join(path, "*"))
        files = [os.path.basename(e) for e in entries if os.path.isfile(e)]
        dirs = [e for e in entries if os.path.isdir(e) and (lvl > 0 or os.path.basename(e) != "lib")]
        # base case: empty dir -> not a command
        if "command.py" not in files and not dirs:
            return None
        # commands that are not installed
        name: str = os.path.basename(path)
        # load subcommands
        subcmds = {}
        for d in dirs:
            cmd_name: str = os.path.basename(d)
            cmd_package = f"{selector}.{cmd_name}".lstrip(".")
            f = self._find_commands(lvl + 1, all_commands, cmd_package, d)
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
                configuration=DTCommandConfigurationDefault,
                environment=None
            )
        # ---
        return subcmds
