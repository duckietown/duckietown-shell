import argparse
from typing import Optional, List

from dt_shell.commands import DTCommandConfigurationAbs


class DTCommandConfiguration(DTCommandConfigurationAbs):

    @classmethod
    def parser(cls, **kwargs) -> Optional[argparse.ArgumentParser]:
        parser: argparse.ArgumentParser = argparse.ArgumentParser()
        parser.add_argument("--staging", action="store_true", default=False, help="Use staging distros")
        parser.add_argument("--unstable", action="store_true", default=False, help="Use unstable distros")
        # ---
        return parser

    @classmethod
    def aliases(cls) -> List[str]:
        return []
