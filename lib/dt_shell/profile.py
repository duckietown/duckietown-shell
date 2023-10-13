import dataclasses
import os.path
import time
from typing import Optional, List, Dict, Union, Iterator, Tuple, Type

import questionary
from questionary import Choice

from dt_authentication import DuckietownToken
from . import logger
from .commands import CommandSet, CommandDescriptor
from .commands.repository import CommandsRepository
from .constants import DUCKIETOWN_TOKEN_URL, SHELL_LIB_DIR, DEFAULT_COMMAND_SET_REPOSITORY, \
    DEFAULT_PROFILES_DIR, DB_SECRETS, DB_SECRETS_DOCKER, DB_SETTINGS, DB_USER_COMMAND_SETS_REPOSITORIES, \
    DB_PROFILES, KNOWN_DISTRIBUTIONS, SUGGESTED_DISTRIBUTION, DB_UPDATES_CHECK
from .database.database import DTShellDatabase, NOTSET, DTSerializable
from .utils import safe_pathname, validator_token, yellow_bold, cli_style


@dataclasses.dataclass
class GenericCredentials(DTSerializable):

    username: str
    password: str

    @property
    def secret(self) -> str:
        return self.password

    def dump(self) -> dict:
        return {"username": self.username, "password": self.password}

    @classmethod
    def load(cls, v: dict) -> 'GenericCredentials':
        return GenericCredentials(**v)


class DockerCredentials(DTShellDatabase[dict]):

    @classmethod
    def load(cls, location: str):
        return DockerCredentials.open(DB_SECRETS_DOCKER, location=location)

    def get(self, registry: str, default: GenericCredentials = NOTSET) -> GenericCredentials:
        try:
            d: dict = super(DockerCredentials, self).get(key=registry)
            return GenericCredentials.load(d)
        except DTShellDatabase.NotFound:
            if default is NOTSET:
                raise DTShellDatabase.NotFound(f"No credentials found for registry '{registry}' in database.")
            else:
                return default

    def set(self, registry: str, value: GenericCredentials):
        super(DockerCredentials, self).set(registry, value.dump())


class ShellProfileSecrets(DTShellDatabase):

    @classmethod
    def load(cls, location: str):
        return ShellProfileSecrets.open(DB_SECRETS, location=location)

    @property
    def dt_token(self) -> Optional[str]:
        return self.dt2_token

    @dt_token.setter
    def dt_token(self, value: str):
        self.dt2_token = value

    @property
    def dt1_token(self) -> Optional[str]:
        return self.get("token/dt1", None)

    @dt1_token.setter
    def dt1_token(self, value: str):
        assert isinstance(value, str)
        self.set("token/dt1", value)

    @property
    def dt2_token(self) -> Optional[str]:
        return self.get("token/dt2", None)

    @dt2_token.setter
    def dt2_token(self, value: str):
        assert isinstance(value, str)
        self.set("token/dt2", value)

    @property
    def docker_credentials(self) -> DockerCredentials:
        return DockerCredentials.load(self._location)


class ShellProfileSettings(DTShellDatabase):

    @classmethod
    def load(cls, location: str):
        return ShellProfileSettings.open(DB_SETTINGS, location=location)

    @property
    def distro(self) -> Optional[str]:
        return self.get("distro", None)

    @distro.setter
    def distro(self, value: str):
        assert isinstance(value, str)
        self.set("distro", value)

    @property
    def check_for_updates(self) -> bool:
        return self.get("check_for_updates", True)

    @check_for_updates.setter
    def check_for_updates(self, value: bool):
        assert isinstance(value, bool)
        self.set("check_for_updates", value)

    @property
    def auto_update(self) -> bool:
        return self.get("auto_update", True)

    @auto_update.setter
    def auto_update(self, value: bool):
        assert isinstance(value, bool)
        self.set("auto_update", value)


@dataclasses.dataclass
class ShellProfile:
    name: str
    path: Optional[str] = None
    command_sets: List[CommandSet] = dataclasses.field(default_factory=list)
    readonly: bool = False

    def __post_init__(self):
        # load from disk
        if self.path is None:
            profiles_dir: str = os.environ.get("DTSHELL_PROFILES", DEFAULT_PROFILES_DIR)
            if profiles_dir != DEFAULT_PROFILES_DIR:
                logger.info(f"Loading profiles from '{profiles_dir}' as prescribed by the environment "
                            f"variable DTSHELL_PROFILES.")
            safe_name: str = safe_pathname(self.name)
            self.path = os.path.join(profiles_dir, safe_name)
            # make sure the profile directory exists
            if not os.path.exists(self.path) and not self.readonly:
                os.makedirs(self.path)

        # add profile to database
        if not self.readonly:
            # record new profile
            db: DTShellDatabase = DTShellDatabase.open(DB_PROFILES)
            if not db.contains(self.name):
                db.set(self.name, self.path)

        # updates check database
        self.updates_check_db: DTShellDatabase[float] = self.database(DB_UPDATES_CHECK)

        # we always start with core commands that are embedded into the shell
        self.command_sets: List[CommandSet] = [
            CommandSet(
                "embedded",
                os.path.join(SHELL_LIB_DIR, "embedded"),
                profile=self,
                leave_alone=True,
            )
        ]

        # load command sets
        if "DTSHELL_COMMANDS" in os.environ:
            commands_path = os.environ["DTSHELL_COMMANDS"]
            # make sure the given path exists
            if not os.path.exists(commands_path):
                msg = f"The path {commands_path} given with the environment variable DTSHELL_COMMANDS does " \
                      f"not exist."
                raise Exception(msg)
            # load commands from given path
            msg = f"Loading commands from '{commands_path}' as instructed by the environment variable " \
                  f"DTSHELL_COMMANDS."
            logger.info(msg)
            self.command_sets.append(
                CommandSet(
                    "development",
                    commands_path,
                    profile=self,
                    repository=CommandsRepository.from_file_system(commands_path),
                    leave_alone=True,
                )
            )
        else:
            profile_command_sets_dir: str = os.path.join(self.path, "commands")
            # add the default 'duckietown' command set
            repository: CommandsRepository = CommandsRepository(
                **DEFAULT_COMMAND_SET_REPOSITORY,
                branch=self.distro,
            )
            self.command_sets.append(
                CommandSet(
                    "duckietown",
                    os.path.join(profile_command_sets_dir, "duckietown"),
                    profile=self,
                    repository=repository,
                )
            )
            # add user defined command sets
            for n, r in self.user_command_sets_repositories:
                self.command_sets.append(CommandSet(n, os.path.join(profile_command_sets_dir, n), self, r))

    @property
    def commands(self) -> Dict[str, Union[dict, CommandDescriptor]]:
        # collapse all command sets into a single tree of commands
        cmds = {}
        for cmd_set in self.command_sets:
            cmds.update(cmd_set.commands)
        return cmds

    @property
    def _databases_location(self) -> str:
        return os.path.join(self.path, "databases")

    @property
    def user_command_sets_repositories(self) -> Iterator[Tuple[str, CommandsRepository]]:
        return self.database(DB_USER_COMMAND_SETS_REPOSITORIES).items()

    @property
    def settings(self) -> ShellProfileSettings:
        return ShellProfileSettings.load(location=self._databases_location)

    @property
    def secrets(self) -> ShellProfileSecrets:
        return ShellProfileSecrets.load(location=self._databases_location)

    @property
    def distro(self) -> Optional[str]:
        return self.settings.distro

    @distro.setter
    def distro(self, value: str):
        self.settings.distro = value

    def database(self, name: str, cls: Optional[Type[DTShellDatabase]] = None) -> DTShellDatabase:
        if cls is None:
            cls = DTShellDatabase
        return cls.open(name, location=self._databases_location)

    def needs_update(self, key: str, period: float, default: bool = True) -> bool:
        # read record
        try:
            last_time_checked: float = self.updates_check_db.get(key)
        except DTShellDatabase.NotFound:
            return default
        # check time
        return time.time() - last_time_checked > period

    def mark_updated(self, key: str, when: float = None):
        # update record
        self.updates_check_db.set(key, when if when is not None else time.time())

    def configure(self):
        # make sure we have a distro for this profile
        if self.distro is None:
            # see if we can find the distro ourselves
            matched: bool = False
            for distro in KNOWN_DISTRIBUTIONS:
                if distro.name == self.name:
                    logger.info(f"Automatically selecting distribution '{distro.name}' as it matches "
                                f"the profile name")
                    self.distro = self.name
                    matched = True

            # if we don't have a match, we ask the user to pick a distribution
            if not matched:
                print()
                print("You need to choose the distribution you want to work with in this profile.")
                distros: List[Choice] = []
                for distro in KNOWN_DISTRIBUTIONS:
                    eol: str = "" if distro.end_of_life is None else \
                        f"(end of life: {distro.end_of_life_fmt})"
                    label = [("class:choice", distro.name), ("class:disabled", f"  {eol}")]
                    choice: Choice = Choice(title=label, value=distro.name)
                    if distro.name == SUGGESTED_DISTRIBUTION:
                        distros.insert(0, choice)
                    else:
                        distros.append(choice)
                # let the user choose the distro
                distro = questionary.select(
                    "Choose a distribution:", choices=distros, style=cli_style).unsafe_ask()
                # attach distro to profile
                self.distro = distro

        # make sure we have a token for this profile
        if self.secrets.dt2_token is None:
            print()
            print(f"The Duckietown Shell needs a Duckietown Token to work properly. "
                  f"Get yours for free at {DUCKIETOWN_TOKEN_URL}")
            # let the user insert the token
            token_str: str = questionary.password("Enter your token:", validate=validator_token).unsafe_ask()
            token: DuckietownToken = DuckietownToken.from_string(token_str)
            # TODO: here we make sure this is a dt2 token (dt1 can be used otherwise)
            print(f"Token verified successfully. Your ID is: {yellow_bold(token.uid)}")
            # store token
            self.secrets.dt2_token = token_str
