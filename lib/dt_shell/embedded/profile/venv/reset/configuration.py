import argparse
from typing import Optional, List

from dt_shell.commands import DTCommandConfigurationAbs


class DTCommandConfiguration(DTCommandConfigurationAbs):

    @classmethod
    def parser(cls, **kwargs) -> Optional[argparse.ArgumentParser]:
        parser: argparse.ArgumentParser = argparse.ArgumentParser()
        # ---
        return parser

    @classmethod
    def aliases(cls) -> List[str]:
        return ["ls"]
