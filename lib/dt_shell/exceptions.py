import sys
from typing import Optional, List, Any, Union

from . import __version__


class NotFound(Exception):
    pass


class InvalidEnvironment(Exception):
    pass


class InvalidRemote(Exception):
    pass


class UserError(Exception):
    """an error that will be briefly printed"""
    pass


class UserAborted(KeyboardInterrupt):
    """the user interrupted the execution"""
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
        from .utils import parse_version

        exc = ShellNeedsUpdate(needed)
        vnow = parse_version(exc.current_version)
        vneed = parse_version(needed)
        if vneed > vnow:
            raise exc


class ShellInitException(Exception):

    def __init__(self,
                 msg: str,
                 stdout: Optional[Union[str, bytes]] = None,
                 stderr: Optional[Union[str, bytes]] = None):
        from dt_shell.logging import dts_print
        # write stdout
        if stdout:
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8")
            dts_print(stdout, color="red")
            sys.stdout.flush()
        # write stderr
        if stderr:
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8")
            sys.stderr.write(stderr)
            sys.stderr.flush()
        # store message
        super(ShellInitException, self).__init__(msg)


class CommandNotFound(Exception):

    def __init__(self, last_matched: Optional[Any], remaining: List[str]):
        from dt_shell import DTCommandAbs
        self.last_matched: Optional[DTCommandAbs] = last_matched
        self.remaining: List[str] = remaining


class RunCommandException(RuntimeError):

    def __init__(self, msg: str, exit_code: int, stdout: str, stderr: str):
        self.msg: str = msg
        self.exit_code: int = exit_code
        self.stdout: str = stdout
        self.stderr: str = stderr
        super(RunCommandException, self).__init__(msg)
