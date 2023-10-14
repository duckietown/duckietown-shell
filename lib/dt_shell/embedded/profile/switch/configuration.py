import argparse
from typing import Optional, List

from dt_shell.commands import DTCommandConfigurationAbs


class DTCommandConfiguration(DTCommandConfigurationAbs):

    @classmethod
    def parser(cls, **kwargs) -> Optional[argparse.ArgumentParser]:
        parser: argparse.ArgumentParser = argparse.ArgumentParser()
        parser.add_argument("profile", nargs="?", default=None, help="Name of the profile to switch to")
        # ---
        return parser

    @classmethod
    def aliases(cls) -> List[str]:
        return []
