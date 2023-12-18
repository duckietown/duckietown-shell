import logging
from typing import List

from dt_shell import DTCommandAbs


__all__ = ["DTCommand"]

from dt_shell import DTShell, logger


class DTCommand(DTCommandAbs):

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # set the internal logger to print INFO messages
        logger.setLevel(logging.INFO)
        # update commands
        shell.update_commands()
