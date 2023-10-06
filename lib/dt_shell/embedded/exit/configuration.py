import argparse
from typing import Optional, List

from dt_shell.commands import DTCommandConfigurationAbs
from dt_shell.environments import Python3Environment, ShellCommandEnvironmentAbs


class DTCommandConfiguration(DTCommandConfigurationAbs):

    @classmethod
    def environment(cls, **kwargs) -> Optional[ShellCommandEnvironmentAbs]:
        return Python3Environment()

    @classmethod
    def parser(cls, **kwargs) -> Optional[argparse.ArgumentParser]:
        pass

    @classmethod
    def aliases(cls) -> List[str]:
        return ["quit"]
