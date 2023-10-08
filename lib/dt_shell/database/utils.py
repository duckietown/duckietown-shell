import os
from typing import Optional

from .database import DTShellDatabase


class InstalledDependenciesDatabase(DTShellDatabase):

    @classmethod
    def load(cls, profile):
        from ..profile import ShellProfile
        profile: ShellProfile
        # ---
        name: str = "installed_dependencies"
        return profile.database(name, cls=InstalledDependenciesDatabase)

    def contains(self, dependencies_fpath: Optional[str]) -> bool:
        # no dependencies filepath? => do no have it
        if dependencies_fpath is None:
            return False
        dependencies_fpath: str = os.path.abspath(dependencies_fpath)
        return super(InstalledDependenciesDatabase, self).contains(dependencies_fpath)

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
