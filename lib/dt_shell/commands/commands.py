import argparse
import dataclasses
import glob
import inspect
import json
import os
import time
from abc import ABCMeta, abstractmethod
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Dict, Type, Union, Optional, Mapping

from ..checks.version import get_url
from .repository import CommandsRepository
from .. import logger
from ..constants import CHECK_CMDS_UPDATE_MINS
from ..environments import ShellCommandEnvironmentAbs, Python3Environment
from ..exceptions import UserError, InvalidRemote, CommandsLoadingException
from ..utils import run_cmd, undo_replace_spaces


CommandName = str
CommandsTree = Dict[CommandName, Union[None, Mapping[CommandName, dict], 'CommandDescriptor']]


class DTCommandAbs(metaclass=ABCMeta):
    name: str = None
    level: int = None
    help: str = None
    commands: CommandsTree = None
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


class DTCommandConfigurationDefault(DTCommandConfigurationAbs):
    pass


@dataclass
class DTCommandSetConfigurationAbs(metaclass=ABCMeta):

    @classmethod
    def default_environment(cls, **kwargs) -> Optional[ShellCommandEnvironmentAbs]:
        """
        The environment in which the commands in this set will run.
        """
        return None

    @classmethod
    def requirements(cls, **kwargs) -> Optional[str]:
        """
        File containing the list of dependency python projects needed by the commands in this command set.
        """
        command_set_metadir: str = os.path.dirname(os.path.abspath(inspect.getfile(cls)))
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


class NoOpCommand(DTCommandAbs):
    @staticmethod
    def command(shell, args, **kwargs):
        pass


class FailedToLoadCommand(NoOpCommand):
    @staticmethod
    def command(shell, args, **kwargs):
        logger.warning("This command was not loaded")


noop_command = SimpleNamespace(DTCommand=NoOpCommand)
failed_to_load_command = SimpleNamespace(DTCommand=FailedToLoadCommand)
default_command_configuration = SimpleNamespace(DTCommandConfiguration=DTCommandConfigurationDefault)
default_commandset_configuration = SimpleNamespace(DTCommandSetConfiguration=DTCommandSetConfigurationDefault)


@dataclass
class CommandSet:
    name: str
    path: str
    repository: Optional[CommandsRepository] = None
    leave_alone: bool = False
    configuration: Type[DTCommandSetConfigurationAbs] = None
    commands: CommandsTree = dataclasses.field(default_factory=dict)

    def __post_init__(self):
        from .importer import import_commandset_configuration

        # load command configuration
        self.configuration: Type[DTCommandSetConfigurationAbs] = import_commandset_configuration(self)
        # load commands
        self.commands = self._find_commands()

    def download(self) -> bool:
        """Raises InvalidRemote if it cannot find it"""
        if self.repository is None:
            raise RuntimeError("You cannot 'download' a command set without a repository defined.")
        # ---
        remote_url = self.repository.remoteurl()
        try:
            logger.info(f"Downloading Duckietown shell commands in {self.path} ...")
            # clone the repo
            run_cmd([
                "git",
                "clone",
                "--branch", self.repository.branch,
                "--recurse-submodules",
                remote_url, self.path
            ])
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
            logger.warning(msg)
            # we can download
            try:
                self.download()
            except InvalidRemote as e:
                msg = "I could not initialize the commands."
                raise CommandsLoadingException(msg) from e
        # make sure the commands exist
        if not os.path.exists(self.path):
            raise UserError(f"Commands not found at '{self.path}'.")

    def ensure_commands_updated(self) -> bool:
        return self.update_cached_commands()

    def commands_need_update(self) -> bool:
        # command sets without repository cannot be updated
        if self.repository is None:
            return False
        # ---
        need_update = False
        # Get the current repo info
        #TODO: use databases instead
        commands_update_check_flag = os.path.join(self.path, ".updates-check")

        # Check if it's time to check for an update
        if os.path.exists(commands_update_check_flag) and os.path.isfile(commands_update_check_flag):
            now = time.time()
            last_time_checked = os.path.getmtime(commands_update_check_flag)
            use_cached_commands = now - last_time_checked < CHECK_CMDS_UPDATE_MINS * 60
        else:  # Save the initial .update flag
            local_sha: str = run_cmd(["git", "-C", self.path, "rev-parse", "HEAD"])
            # noinspection PyTypeChecker
            local_sha = next(filter(len, local_sha.split("\n")))
            self.save_update_check_flag(local_sha)
            return False

        # Check for an updated remote
        if not use_cached_commands:
            # Get the local sha from file (ok if oos from manual pull)
            with open(commands_update_check_flag, "r") as fp:
                try:
                    cached_check = json.load(fp)
                except ValueError:
                    return False
                local_sha = cached_check["remote"]

            # Get the remote sha from GitHub
            logger.info("Fetching remote SHA from github.com ...")
            remote_url: str = "https://api.github.com/repos/%s/%s/branches/%s" % (
                self.repository.username,
                self.repository.project,
                self.repository.branch,
            )
            try:
                content = get_url(remote_url)
                data = json.loads(content)
                remote_sha = data["commit"]["sha"]
            except Exception as e:
                logger.error(str(e))
                return False

            # check if we need to update
            need_update = local_sha != remote_sha
            # touch flag to reset update check time
            self.touch_update_check_flag()

        return need_update

    def save_update_check_flag(self, sha: str):
        # TODO: use databases instead
        commands_update_check_flag = os.path.join(self.path, ".updates-check")
        with open(commands_update_check_flag, "w") as fp:
            json.dump({"remote": sha}, fp)

    def touch_update_check_flag(self):
        # TODO: use databases instead
        commands_update_check_flag = os.path.join(self.path, ".updates-check")
        with open(commands_update_check_flag, "a"):
            os.utime(commands_update_check_flag, None)

    def update_cached_commands(self) -> bool:
        # make sure the commands directory exists
        if not os.path.exists(self.path) and os.path.isdir(self.path):
            raise RuntimeError(f"There is no existing commands directory in '{self.path}'.")

        # command sets without repository cannot be updated
        if self.repository is None:
            raise RuntimeError("Command sets without a repository defined cannot be updated.")

        # Check for shell commands repo updates
        logger.info("Checking for updates in the Duckietown shell commands repo...")
        if self.commands_need_update():
            logger.info("The Duckietown shell commands have available updates. Attempting to pull them.")
            logger.debug(f"Updating Duckietown shell commands at '{self.path}'...")
            wait_on_retry_secs = 4
            th = {2: "nd", 3: "rd", 4: "th"}
            for trial in range(3):
                try:
                    run_cmd(["git", "-C", self.path, "pull", "--recurse-submodules", "origin",
                             self.repository.branch])
                    logger.debug(f"Updated Duckietown shell commands in '{self.path}'.")
                    logger.info(f"Duckietown shell commands successfully updated!")
                except RuntimeError as e:
                    logger.error(str(e))
                    logger.warning(
                        "An error occurred while pulling the updated commands. Retrying for "
                        f"the {trial + 2}-{th[trial + 2]} in {wait_on_retry_secs} seconds."
                    )
                    time.sleep(wait_on_retry_secs)
                else:
                    break
            run_cmd(["git", "-C", self.path, "submodule", "update"])

            # Get HEAD sha after update and save
            current_sha: str = run_cmd(["git", "-C", self.path, "rev-parse", "HEAD"])
            # noinspection PyTypeChecker
            current_sha = next(filter(len, current_sha.split("\n")))
            self.save_update_check_flag(current_sha)
            return True  # Done updating
        else:
            logger.info(f"Duckietown shell commands are up-to-date.")
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
