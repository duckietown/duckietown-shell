from . import __version__
from .utils import parse_version


__all__ = [
    "NotFound",
    "InvalidEnvironment",
    "UserError",
    "CommandsLoadingException",
    "ConfigNotPresent",
    "ConfigInvalid",
    "CouldNotGetVersion",
    "NoCacheAvailable",
    "URLException",
    "InvalidConfig",
    "InvalidRemote",
    "ShellNeedsUpdate"
]


class NotFound(Exception):
    pass


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


class ShellNeedsUpdate(Exception):
    def __init__(self, needed: str):
        self._version_needed: str = needed
        self._current_version: str = __version__

    @property
    def current_version(self) -> str:
        return self._current_version

    @property
    def version_needed(self) -> str:
        return self._version_needed

    @staticmethod
    def assert_newer_or_equal_to(needed: str):
        exc = ShellNeedsUpdate(needed)
        vnow = parse_version(exc.current_version)
        vneed = parse_version(needed)
        if vneed > vnow:
            raise exc
