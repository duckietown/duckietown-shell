import subprocess
import traceback
from typing import Optional

import termcolor

from . import dtslogger


def indent(s: str, prefix: str, first: Optional[str] = None) -> str:
    s = str(s)
    assert isinstance(prefix, str)
    lines = s.split("\n")
    if not lines:
        return ""

    if first is None:
        first = prefix

    m = max(len(prefix), len(first))

    prefix = " " * (m - len(prefix)) + prefix
    first = " " * (m - len(first)) + first

    # different first prefix
    res = ["%s%s" % (prefix, line.rstrip()) for line in lines]
    res[0] = "%s%s" % (first, lines[0].rstrip())
    return "\n".join(res)


def raise_wrapped(etype, e, msg, compact=False, exc=None, **kwargs):
    """Raises an exception of type etype by wrapping
    another exception "e" with its backtrace and adding
    the objects in kwargs as formatted by format_obs.

    if compact = False, write the whole traceback, otherwise just str(e).

    exc = output of sys.exc_info()
    """

    e = raise_wrapped_make(etype, e, msg, compact=compact, **kwargs)

    #     if exc is not None:
    #         _, _, trace = exc
    #         raise etype, e.args, trace
    #     else:
    raise e


def raise_wrapped_make(etype, e, msg, compact=False, **kwargs):
    """Constructs the exception to be thrown by raise_wrapped()"""
    assert isinstance(e, BaseException), type(e)
    assert isinstance(msg, str), type(msg)
    s = msg

    import sys

    if sys.version_info[0] >= 3:
        es = str(e)
    else:
        if compact:
            es = str(e)
        else:
            es = format_exception(e)

    s += "\n" + indent(es.strip(), "| ")

    return etype(s)


def check_isinstance(ob, expected, **kwargs):
    if not isinstance(ob, expected):
        kwargs["object"] = ob
        raise_type_mismatch(ob, expected, **kwargs)


def raise_type_mismatch(ob, expected, **kwargs):
    """Raises an exception concerning ob having the wrong type."""
    e = "Object not of expected type:"
    e += "\n  expected: %s" % str(expected)
    e += "\n  obtained: %s" % str(type(ob))
    # e += '\n' + indent(format_obs(kwargs), ' ')
    raise ValueError(e)


SPACE_TAG = "SPACE_TAG"


def replace_spaces(x: str) -> str:
    return x.replace(" ", SPACE_TAG)


def undo_replace_spaces(x: str) -> str:
    return x.replace(SPACE_TAG, " ")


def format_exception(e):
    return traceback.format_exc()  # None, e)


def href(x):
    return termcolor.colored(x, "blue", None, ["underline"])


def dark_yellow(x):
    return termcolor.colored(x, "yellow")


def dark(x):
    return termcolor.colored(x, attrs=["dark"])


def run_cmd(cmd, print_output=False, suppress_errors=False):
    dtslogger.debug("$ %s" % cmd)
    # spawn new process
    proc = subprocess.Popen(cmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    stdout = stdout.decode("utf-8") if stdout else None
    stderr = stderr.decode("utf-8") if stderr else None
    returncode = proc.returncode
    # ---
    if returncode != 0 and not suppress_errors:
        msg = "The command %r failed with exit code %d.\nError:\n%s" % (cmd, returncode, stderr)
        raise RuntimeError(msg)
    if print_output:
        print(stdout)
    return stdout
