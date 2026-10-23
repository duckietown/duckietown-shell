import argparse

from dt_shell.commands import DTCommandConfigurationAbs
from dt_shell.environments import Python3Environment


class DTCommandConfiguration(DTCommandConfigurationAbs):
    subcommand: str = ""

    @classmethod
    def environment(cls, *args, **kwargs) -> Python3Environment:
        return Python3Environment()

    @classmethod
    def parser(cls, *args, **kwargs) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog=f"dts developer {cls.subcommand}".rstrip(),
            description="Manage signed staff/superuser authorization for DTS source overrides.",
        )
        return parser
