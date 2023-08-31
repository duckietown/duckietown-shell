import dataclasses


class ShellCommandEnvironmentAbs:
    pass


@dataclasses.dataclass
class Python3Environment(ShellCommandEnvironmentAbs):
    """
    Python3 environment shared with the shell library.
    Default for all the distros up to and including 'daffy'.
    """
    pass


@dataclasses.dataclass
class DockerContainerEnvironment(ShellCommandEnvironmentAbs):
    """
    Each command is run inside a separate container.
    Default for the 'ente' distribution.
    """
    image: str
    configuration: dict = dataclasses.field(default_factory=dict)
