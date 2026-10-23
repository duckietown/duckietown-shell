import os
from typing import Optional

from dt_shell_cli import logger
from .database import DTShellDatabase
from ..constants import DB_INSTALLED_DEPENDENCIES, DTShellConstants
from ..utils import indent_block


class InstalledDependenciesDatabase(DTShellDatabase):

    @classmethod
    def load(cls, venv_dir: str) -> "InstalledDependenciesDatabase":
        location = os.path.join(os.path.abspath(venv_dir), ".dts")
        database = cls.open(DB_INSTALLED_DEPENDENCIES, location=location)
        if not isinstance(database, cls):
            raise TypeError(f"Invalid dependency cache type: {type(database).__name__}")
        return database

    def contains(self, dependencies_fpath: Optional[str]) -> bool:
        # no dependencies filepath? => do no have it
        if dependencies_fpath is None:
            return False
        dependencies_fpath: str = os.path.abspath(dependencies_fpath)
        return super(InstalledDependenciesDatabase, self).contains(dependencies_fpath)

    def needs_install_step(self, dependencies_fpath: Optional[str]) -> bool:
        # no dependencies files => no need to install
        if dependencies_fpath is None:
            return False
        dependencies_fpath: str = os.path.abspath(dependencies_fpath)
        # get current list
        with open(dependencies_fpath, "rt") as fin:
            current: str = fin.read()
        # get list from last installation
        last: str = self.get(dependencies_fpath, "")
        # compare the two
        if DTShellConstants.VERBOSE:
            logger.debug(f"Comparing OLD<>NEW dependencies lists for '{dependencies_fpath}':\n\n"
                         f"OLD:\n|{indent_block(last)}|\n\nNEW:\n|{indent_block(current)}|")
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
