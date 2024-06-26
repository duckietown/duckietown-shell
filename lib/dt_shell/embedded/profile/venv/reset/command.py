import os.path
import shutil
from typing import List

import questionary

from dt_shell import DTCommandAbs, DTShell, dtslogger


class DTCommand(DTCommandAbs):
    help = "Resets the current profile Python's virtual environment"

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # make sure the user known what is doing
        dtslogger.warning(
            "\n"
            "---\n"
            "\n"
            "This operation will delete this profile's virtual environment.\n"
            "This is usually a safe operation as the environment will be recreated the next time the shell is run.\n"
            "\n---"
        )
        proceed: bool = questionary.confirm("Do you want to continue?").ask()
        # ---
        if not proceed:
            dtslogger.info("Operation aborted!")
            return

        # delete virtual environment
        venv_path: str = os.path.join(shell.profile.path, "venv")
        if not os.path.exists(venv_path):
            dtslogger.error(f"The virtual environment was expected to be found at '{venv_path}' but this path "
                            f"does not exist. This should not have happened.")
            return
        dtslogger.info("Deleting virtual environment...")
        dtslogger.debug(f"Removing path '{venv_path}'")
        shutil.rmtree(venv_path)
        dtslogger.info("Virtual environment successfully reset.")

    @staticmethod
    def complete(shell: DTShell, word: str, line: str) -> List[str]:
        return []
