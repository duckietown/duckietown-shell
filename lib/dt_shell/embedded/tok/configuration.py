from typing import List

from dt_shell.commands import DTCommandConfigurationAbs


class DTCommandConfiguration(DTCommandConfigurationAbs):

    @classmethod
    def aliases(cls) -> List[str]:
        return ["token"]
