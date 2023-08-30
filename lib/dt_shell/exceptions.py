__all__ = [
    "InvalidEnvironment",
    "UserError",
    "CommandsLoadingException",
    "ConfigNotPresent",
    "ConfigInvalid",
    "CouldNotGetVersion",
    "NoCacheAvailable",
    "URLException",
    "InvalidConfig",
    "InvalidRemote"
]


class InvalidEnvironment(Exception):
    pass


class InvalidRemote(Exception):
    pass


class UserError(Exception):
    """an error that will be briefly printed"""

    pass


class InvalidConfig(Exception):
    pass


class CommandsLoadingException(Exception):
    pass


class ConfigInvalid(Exception):
    pass


class ConfigNotPresent(Exception):
    pass


class CouldNotGetVersion(Exception):
    pass


class URLException(Exception):
    pass


class NoCacheAvailable(Exception):
    pass
