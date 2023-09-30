import dataclasses
from abc import ABCMeta, abstractmethod
from typing import List


class ShellCommandEnvironmentAbs(metaclass=ABCMeta):

    @abstractmethod
    def execute(self, shell, args: List[str]):
        raise NotImplementedError("Subclasses should implement the function execute()")


@dataclasses.dataclass
class Python3Environment(ShellCommandEnvironmentAbs):
    """
    Python3 environment shared with the shell library.
    Default for all the distros up to and including 'daffy'.
    """

    def execute(self, shell, args: List[str]):
        # TODO: implement this
        raise NotImplementedError("TODO")


@dataclasses.dataclass
class VirtualPython3Environment(ShellCommandEnvironmentAbs):
    """
    Virtual Python3 environment dedicated to a profile and NOT SHARED with the shell library.
    Default for the 'ente' distribution.
    """

    def execute(self, shell, args: List[str]):
        # TODO: implement this
        raise NotImplementedError("TODO")


@dataclasses.dataclass
class DockerContainerEnvironment(ShellCommandEnvironmentAbs):
    """
    Each command is run inside a separate container.
    Supported since the 'ente' distribution.
    """
    image: str
    configuration: dict = dataclasses.field(default_factory=dict)

    def execute(self, shell, args: List[str]):
        # TODO: implement this
        raise NotImplementedError("TODO")


DEFAULT_COMMAND_ENVIRONMENT: ShellCommandEnvironmentAbs = VirtualPython3Environment()
