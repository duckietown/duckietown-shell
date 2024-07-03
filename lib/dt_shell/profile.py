import atexit
import copy
import dataclasses
import json
import os.path
import tempfile
import time
from typing import Optional, List, Dict, Union, Iterator, Tuple, Type

import questionary
from questionary import Choice

from dt_authentication import DuckietownToken
from yaml.scanner import ScannerError

from . import logger, __version__
from .commands import CommandSet, CommandDescriptor
from .commands.repository import CommandsRepository
from .constants import DUCKIETOWN_TOKEN_URL, SHELL_LIB_DIR, DEFAULT_COMMAND_SET_REPOSITORY, \
    DEFAULT_PROFILES_DIR, DB_SECRETS, DB_SECRETS_DOCKER, DB_SETTINGS, DB_USER_COMMAND_SETS_REPOSITORIES, \
    DB_PROFILES, KNOWN_DISTRIBUTIONS, SUGGESTED_DISTRIBUTION, DB_UPDATES_CHECK, EMBEDDED_COMMAND_SET_NAME, \
    Distro
from .database.database import DTShellDatabase, NOTSET, DTSerializable
from .statistics import ShellProfileEventsDatabase
from .utils import safe_pathname, validator_token, yellow_bold, cli_style, parse_version, render_version, \
    indent_block, DebugInfo
from .exceptions import ConfigNotPresent

TupleVersion = Tuple[int, int, int]


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

    def contains(self, registry: str) -> bool:
        return super(DockerCredentials, self).contains(registry)

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

    def __new__(cls, *args, **kwargs):
        inst = super().__new__(cls)
        inst._profile = kwargs["profile"]
        return inst

    @classmethod
    def load(cls, profile: 'ShellProfile', location: str):
        return ShellProfileSecrets.open(DB_SECRETS, location=location, init_args={"profile": profile})

    @property
    def dt_token(self) -> Optional[str]:
        preferred: str = self._profile.distro.token_preferred
        if preferred == "dt1":
            return self.dt1_token
        elif preferred == "dt2":
            return self.dt2_token
        else:
            raise ValueError(f"Token version '{preferred}' not supported")

    @dt_token.setter
    def dt_token(self, value: str):
        preferred: str = self._profile.distro.token_preferred
        if preferred == "dt1":
            self.dt1_token = value
        elif preferred == "dt2":
            self.dt2_token = value
        else:
            raise ValueError(f"Token version '{preferred}' not supported")

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

    @classmethod
    def _as_temporary_file(cls, content: str, autoremove: bool = True) -> str:
        # create temporary file and write content to it
        tmpf_fd, tmpf_fpath = tempfile.mkstemp()
        os.write(tmpf_fd, content.encode("utf-8"))
        os.close(tmpf_fd)
        # when Python exits, the file gets removed
        if autoremove:
            atexit.register(os.remove, tmpf_fpath)
        # ---
        return tmpf_fpath

    def as_temporary_json_file(self, key: str, autoremove: bool = True) -> str:
        secret: dict = self.get(key)
        return self._as_temporary_file(json.dumps(secret), autoremove=autoremove)


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

    _distro: dataclasses.InitVar[str] = None

    def __post_init__(self, _distro: Optional[str] = None):
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

        # set distro if given
        if _distro is not None:
            self.distro = _distro

        # this is the order with which command sets are loaded
        self.command_sets: List[CommandSet] = []

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
            # TODO: this is where we update the profile.distro by taking the branch from the repository but
            #  only for this session
        else:
            profile_command_sets_dir: str = os.path.join(self.path, "commands")
            # add the default 'duckietown' command set
            if self.distro is not None:
                repository: CommandsRepository = CommandsRepository(
                    **{**DEFAULT_COMMAND_SET_REPOSITORY, "branch": self.distro.branch}
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

        # we always add the embedded command set last so that it can override everything the others do
        self.command_sets.append(
            CommandSet(
                EMBEDDED_COMMAND_SET_NAME,
                os.path.join(SHELL_LIB_DIR, "embedded"),
                profile=self,
                leave_alone=True,
            )
        )

        # add command set versions to debugging data
        for cs in self.command_sets:
            DebugInfo.name2versions[f"command_set/{cs.name}"] = cs.version

        # drop all the command sets that do not support this version of the shell
        for cs in copy.copy(self.command_sets):
            vnow: TupleVersion = parse_version(__version__)
            vmin: Optional[TupleVersion] = cs.configuration.minimum_shell_version()
            vmax: Optional[TupleVersion] = cs.configuration.maximum_shell_version()
            # check min
            if vmin is not None and vnow < vmin:
                logger.warning(f"\n -- WARNING\n\n" +
                                indent_block(
                                   f"Command set '{cs.name}' wants a Duckietown Shell v{render_version(vmin)}"
                                   f" or newer. We are running v{render_version(vnow)}.\n"
                                   f"You will need to upgrade your shell to be able to use this command "
                                   f"set or switch to an older version of this command set.\n"
                                   f"This command set will now be disabled."
                                ) +
                               f"\n\n -- WARNING\n")
                self.command_sets.remove(cs)
            # check max
            if vmax is not None and vnow > vmax:
                logger.warning(f"\n -- WARNING\n\n" +
                               indent_block(
                                   f"Command set '{cs.name}' only supports Duckietown Shell up to "
                                   f"v{render_version(vmax)}. We are running v{render_version(vnow)}.\n"
                                   f"You will need to downgrade your shell to be able to use this command "
                                   f"set or switch to a newer version of this command set.\n"
                                   f"This command set will now be disabled."
                               ) +
                               f"\n\n -- WARNING\n")
                self.command_sets.remove(cs)

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
        return ShellProfileSecrets.load(profile=self, location=self._databases_location)

    @property
    def events(self) -> ShellProfileEventsDatabase:
        try:
            db = ShellProfileEventsDatabase.load(location=self._databases_location)
        except ScannerError:
            logger.warning("The statistics/events database appears to be corrupted. It will be reset.")
            db = ShellProfileEventsDatabase.reset(location=self._databases_location)
        return db

    @property
    def distro(self) -> Optional[Distro]:
        if self.settings.distro is None:
            return None
        if self.settings.distro not in KNOWN_DISTRIBUTIONS:
            logger.warning(f"Your profile is set to use the distribution '{self.settings.distro}' but this "
                           f"is not in the list of known distributions. Known distributions are "
                           f"{list(KNOWN_DISTRIBUTIONS.keys())}")
            return None
        return KNOWN_DISTRIBUTIONS[self.settings.distro]

    @distro.setter
    def distro(self, value: Union[str, Distro]):
        if isinstance(value, Distro):
            value = value.name
        assert value in KNOWN_DISTRIBUTIONS
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

    def configure(self, readonly: bool = False) -> bool:
        modified_config: bool = False
        # make sure we have a distro for this profile
        if self.distro is None:
            if readonly:
                raise ConfigNotPresent()
            # see if we can find the distro ourselves
            matched: bool = False
            for d in KNOWN_DISTRIBUTIONS.keys():
                if d == self.name:
                    logger.info(f"Automatically selecting distribution '{d}' as it matches the profile name")
                    self.distro = d
                    matched = True
                    break

            # if we don't have a match, we ask the user to pick a distribution
            if not matched:
                print()
                print("You need to choose the distribution you want to work with in this profile.")
                distros: List[Choice] = []
                for distro in KNOWN_DISTRIBUTIONS.values():
                    # only show production branches
                    if distro.staging:
                        continue
                    # only show stable distributions
                    if not distro.stable:
                        continue
                    # ---
                    eol: str = "" if distro.end_of_life is None else \
                        f"(end of life: {distro.end_of_life_fmt})"
                    label = [("class:choice", distro.name), ("class:disabled", f"  {eol}")]
                    choice: Choice = Choice(title=label, value=distro.name)
                    if distro.name == SUGGESTED_DISTRIBUTION:
                        distros.insert(0, choice)
                    else:
                        distros.append(choice)
                # let the user choose the distro
                chosen_distro: str = questionary.select(
                    "Choose a distribution:", choices=distros, style=cli_style).unsafe_ask()
                # attach distro to profile
                self.distro = chosen_distro
            modified_config = True

        # make sure we have a token for this profile
        if self.secrets.dt_token is None:
            if readonly:
                raise ConfigNotPresent()
            print()
            print(f"The Duckietown Shell needs a Duckietown Token to work properly. "
                  f"Get yours for free at {DUCKIETOWN_TOKEN_URL}")
            while True:
                # let the user insert the token
                token_str: str = questionary.password("Enter your token:", validate=validator_token)\
                    .unsafe_ask()
                token: DuckietownToken = DuckietownToken.from_string(token_str)
                # make sure this token is supported by this profile distro
                tokens_supported: List[str] = self.distro.tokens_supported
                if token.version not in tokens_supported:
                    print(f"Token version '{token.version}' not supported by this profile's distro. "
                          f"Only versions supported are {tokens_supported}.")
                    continue
                else:
                    print(f"Token verified successfully. Your ID is: {yellow_bold(token.uid)}")
                    break
            # store token
            self.secrets.dt_token = token_str
            modified_config = True
        # ---
        return modified_config
