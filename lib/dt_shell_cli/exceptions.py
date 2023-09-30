import sys
from typing import Optional


class ShellInitException(Exception):

    def __init__(self, msg: str, stdout: Optional[str] = None, stderr: Optional[str] = None):
        # write stdout
        if stdout:
            sys.stdout.write(stdout)
            sys.stdout.flush()
        # write stderr
        if stderr:
            sys.stderr.write(stderr)
            sys.stderr.flush()
        # store message
        super(ShellInitException, self).__init__(msg)
