# used by the following commands files:
#
#   - update/command.py
#
import os
from types import SimpleNamespace

from .config import ShellConfig, read_shell_config


class OtherVersions:

    @classmethod
    @property
    def name2versions(cls):
        from dt_shell.utils import DebugInfo
        return DebugInfo.name2versions


def apply(shell):
    """
    Applies backward compatibility edits to an instance of the shell
    """

    def get_dt1_token(self) -> str:
        var = "token_dt1"
        from_env = os.environ.get(var, None)
        if from_env:
            msg = f"Using token from environment variable {var} instead of config."
            print(msg)
            return from_env
        if self.profile.secrets.dt1_token is None:
            msg = 'Please set up a token for this using "dts tok set".'
            raise Exception(msg)
        else:
            return self.profile.secrets.dt1_token

    def get_commands_version(self) -> str:
        return self.profile.name

    @property
    def shell_config(self) -> ShellConfig:
        return read_shell_config()

    def save_config(self):
        # TODO: implement this by taking the info from .config._instance and updating shell.secrets...
        pass

    # add methods to the given shell instance
    shell.get_dt1_token = get_dt1_token
    shell.get_commands_version = get_commands_version
    shell.shell_config = shell_config
    shell.save_config = save_config
    shell.local_commands_info = SimpleNamespace(leave_alone=False)
