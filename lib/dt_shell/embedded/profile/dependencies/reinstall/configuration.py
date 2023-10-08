import argparse
from typing import Optional, List

from dt_shell.commands import DTCommandConfigurationAbs


class DTCommandConfiguration(DTCommandConfigurationAbs):

    @classmethod
    def parser(cls, **kwargs) -> Optional[argparse.ArgumentParser]:
        pass

    @classmethod
    def aliases(cls) -> List[str]:
        return []
