import os.path
import subprocess
import sys
from typing import Optional

from dt_shell.database import DTShellDatabase
from dt_shell.profile import ShellProfile
from dt_shell_cli.exceptions import ShellInitException


class InstalledDependenciesDatabase(DTShellDatabase):

    @classmethod
    def load(cls, profile: ShellProfile):
        name: str = "installed_dependencies"
        return profile.database(name, cls=InstalledDependenciesDatabase)

    def needs_install_step(self, dependencies_fpath: Optional[str]) -> bool:
        # no dependencies files no need to install
        if dependencies_fpath is None:
            return False
        dependencies_fpath: str = os.path.abspath(dependencies_fpath)
        # get current list
        with open(dependencies_fpath, "rt") as fin:
            current: str = fin.read()
        # get list from last installation
        last: str = self.get(dependencies_fpath, "")
        # compare the two
        return current != last

    def mark_as_installed(self, dependencies_fpath: Optional[str]):
        # no dependencies files no need to install
        if dependencies_fpath is None:
            return
        dependencies_fpath: str = os.path.abspath(dependencies_fpath)
        # get current list
        with open(dependencies_fpath, "rt") as fin:
            current: str = fin.read()
        # set list as last installation
        self.set(dependencies_fpath, current)


def pip_install(interpreter: str, requirements: str):
    try:
        subprocess.check_output(
            [interpreter, "-m", "pip", "install", "-r", requirements], stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        msg: str = "An error occurred while installing python dependencies"
        raise ShellInitException(msg, stdout=e.stdout, stderr=e.stderr)
