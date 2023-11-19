import sys
from typing import Optional, List

from dt_shell import DTCommandAbs, DTShell, dtslogger
from dt_shell.constants import SHELL_REQUIREMENTS_LIST
from dt_shell.database.utils import InstalledDependenciesDatabase
from dt_shell.utils import pip_install


class DTCommand(DTCommandAbs):

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # install dependencies
        cache: InstalledDependenciesDatabase = InstalledDependenciesDatabase.load(shell.profile)
        # - shell
        dtslogger.info("Installing shell dependencies...")
        pip_install(sys.executable, SHELL_REQUIREMENTS_LIST)
        cache.mark_as_installed(SHELL_REQUIREMENTS_LIST)
        # - command sets
        for cs in shell.command_sets:
            requirements_list: Optional[str] = cs.configuration.requirements()
            dtslogger.info(f"Installing dependencies for command set '{cs.name}'...")
            pip_install(sys.executable, requirements_list)
            cache.mark_as_installed(requirements_list)
