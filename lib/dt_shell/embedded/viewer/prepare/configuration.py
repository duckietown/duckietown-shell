import argparse
from dt_shell.commands import DTCommandConfigurationAbs
from dt_shell.viewer_runtime import APPS


class DTCommandConfiguration(DTCommandConfigurationAbs):
    @classmethod
    def parser(cls, *args, **kwargs):
        parser = argparse.ArgumentParser()
        parser.add_argument("--app", required=True, choices=APPS)
        parser.add_argument("--url", default="http://localhost:8000/app/")
        parser.add_argument("--directory", required=True)
        parser.add_argument("--broker-host", default="127.0.0.1")
        return parser
