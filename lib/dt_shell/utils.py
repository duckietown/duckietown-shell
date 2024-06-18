import logging
import os
import sys
import platform
import re
import shutil
import subprocess
import importlib
import locale
import json
import yaml
import traceback
from math import floor
from traceback import format_exc
from typing import Optional, Any, Tuple, List, Dict, Union

import termcolor
from termcolor import colored
from questionary import Style

import dt_authentication
from dt_authentication import DuckietownToken

from dt_shell_cli import logger
from . import __version__
from .constants import BASH_COMPLETION_DIR, SHELL_LIB_DIR, DTShellConstants
from .exceptions import ShellInitException, RunCommandException

NOTSET = object()


cli_style = Style([
    ('qmark', 'fg:#673ab7 bold'),        # token in front of the question
    ('question', 'bold'),                # question text
    ('choice', 'fg:#fec20b bold'),       # a possible choice in select
    ('answer', 'fg:#fec20b bold'),       # submitted answer text behind the question
    ('pointer', 'fg:#673ab7 bold'),      # pointer used in select and checkbox prompts
    ('highlighted', 'fg:#673ab7 bold'),  # pointed-at choice in select and checkbox prompts
    ('selected', 'fg:#cc5454'),          # style for a selected item of a checkbox
    ('separator', 'fg:#cc5454'),         # separator in lists
    ('instruction', ''),                 # user instructions for select, rawselect, checkbox
    ('text', ''),                        # plain text
    ('disabled', 'fg:#bbbbbb italic')    # disabled choices for select and checkbox prompts
])


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
            es = format_exc()

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


def href(x):
    return termcolor.colored(x, "blue", None, ["underline"])


def dark_yellow(x):
    return termcolor.colored(x, "yellow")


def dark(x):
    return termcolor.colored(x, attrs=["dark"])


def safe_pathname(s: str) -> str:
    return re.sub(r"[^\w\d-]", "_", s)


def run_cmd(cmd, print_output=False, suppress_errors=False):
    logger.debug("$ %s" % cmd)
    # spawn new process
    proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    stdout = stdout.decode("utf-8") if stdout else None
    stderr = stderr.decode("utf-8") if stderr else None
    returncode = proc.returncode
    # ---
    if returncode != 0 and not suppress_errors:
        msg = "The command %r failed with exit code %d.\nError:\n%s\nOutput:\n%s\n" % (
            cmd, returncode, indent_block(stderr), indent_block(stdout))
        raise RunCommandException(msg, returncode, stdout, stderr)
    if print_output:
        print(stdout)
    return stdout


def parse_version(x: str):
    return tuple(int(_) for _ in x.split("."))


def render_version(t: Tuple[int, int, int]):
    return ".".join(str(_) for _ in t)


def load_class(name: str, module: str, package: Optional[str] = None) -> Any:
    logger.debug(f"Loading class {package or ''}.{module}.{name}")
    mod = importlib.import_module(name=module, package=package)
    return getattr(mod, name)


def provider_username_project_from_git_url(url: str) -> Tuple[str, str, str]:
    ssh_pattern = "git@([^:]+):([^/]+)/(.+)"
    res = re.search(ssh_pattern, url, re.IGNORECASE)
    if res:
        return res.group(1), res.group(2), res.group(3)
    https_pattern = "https://([^/]+)/([^/]+)/(.+)"
    res = re.search(https_pattern, url, re.IGNORECASE)
    if res:
        return res.group(1), res.group(2), res.group(3)


def ln(s: str) -> int:
    """
    Computes the length of a string while taking into account the coloring characters.
    """
    return len(re.sub(rb"(\x1b|\[\d{1,2}m)*", b"", s.encode("utf-8")))


def text_distribute(chunks: List[str], width: int) -> str:
    remaining: int = width - sum(map(ln, chunks))
    spaces: List[int] = [0] + [int(floor(remaining / (len(chunks) - 1)))] * (len(chunks) - 1)
    spaces[-1] += remaining - sum(spaces)

    txt: str = ""
    for s, t in zip(spaces, chunks):
        txt += f"{' ' * s}{t}"
    return txt


def text_justify(txt: str, width: int) -> str:
    return "\n".join(
        [" " * int(floor((width - ln(line)) / 2)) + line for line in txt.splitlines(keepends=False)]
    )


def validator_token(token: str) -> bool:
    try:
        DuckietownToken.from_string(token, allow_expired=False)
    except dt_authentication.exceptions.InvalidToken as e:
        # logger.error(f"The given token is not valid: {str(e)}")
        return False
    except dt_authentication.exceptions.ExpiredToken:
        # logger.warning(f"The given token is expired, make sure you get a fresh one before continuing.")
        return False
    # ---
    return True


def yellow_bold(x: Any) -> str:
    return colored(str(x), color="yellow", attrs=["bold"])


class DebugInfo:
    name2versions: Dict[str, Union[str, Dict[str, str]]] = {}


def pip_install(interpreter: str, requirements: str):
    run = subprocess.check_call if logger.level <= logging.DEBUG else subprocess.check_output
    try:
        run(
            [interpreter, "-m", "pip", "install", "-r", requirements],
            stderr=subprocess.STDOUT,
            env={}
        )
    except subprocess.CalledProcessError as e:
        msg: str = "An error occurred while installing python dependencies"
        raise ShellInitException(msg, stdout=e.stdout, stderr=e.stderr)


def indent_block(s: str, indent_len: int = 4) -> str:
    space: str = " " * indent_len
    return space + f"\n{space}".join(s.splitlines() if s is not None else ["None"])


def pretty_json(data: Any, indent_len: int = 0) -> str:
    return indent_block(json.dumps(data, sort_keys=True, indent=4), indent_len=indent_len)


def pretty_exc(exc: Exception, indent_len: int = 0) -> str:
    return indent_block(
        ''.join(traceback.TracebackException.from_exception(exc).format()), indent_len=indent_len)


def ensure_bash_completion_installed():
    import dt_shell
    from dt_shell.database import DTShellDatabase
    if platform.system() in ["Linux", "Darwin"]:
        db: DTShellDatabase = DTShellDatabase.open("bash-completion-install")
        key: str = f"dts-comletion-{dt_shell.__version__}"
        if not db.contains(key):
            logger.info("Installing bash-completion script...")
            src: str = os.path.join(SHELL_LIB_DIR, "assets", "dts-completion.bash")
            dst: str = os.path.join(BASH_COMPLETION_DIR, "dts")
            try:
                os.makedirs(BASH_COMPLETION_DIR, exist_ok=True)
                shutil.copyfile(src, dst)
            except Exception:
                logger.warning("An error occurred while attempting to install the bash-completion script")
                if DTShellConstants.VERBOSE:
                    traceback.print_last()
                return
            # mark it as installed in the database
            db.set(key, True)
            logger.info("Bash-completion script successfully installed")
        else:
            logger.debug("Bash-completion script marked as already installed")


def print_debug_info() -> None:
    from .logging import dts_print
    from .checks.packages import _get_installed_distributions

    v = DebugInfo.name2versions
    v["python"] = sys.version
    v["duckietown-shell"] = __version__

    v["encodings"] = {
        "stdout": sys.stdout.encoding,
        "stderr": sys.stderr.encoding,
        "locale": locale.getpreferredencoding(),
    }

    try:
        installed = _get_installed_distributions()
        pkgs = {_.project_name: _.version for _ in installed}
        for pkg_name, pkg_version in pkgs.items():
            include = (
                    ("duckietown" in pkg_name)
                    or ("dockertown" in pkg_name)
                    or ("dt-" in pkg_name)
                    or ("-z" in pkg_name)
                    or ("aido" in pkg_name)
            )
            if include:
                v[pkg_name] = pkg_version
    except (ImportError, AttributeError):
        logger.warning('Please update "pip" to have better debug info.')

    versions = yaml.dump(v, default_flow_style=False)
    fn = "~/shell-debug-info.txt"
    fn = os.path.expanduser(fn)
    with open(fn, "w") as f:
        f.write(versions)
    msg = f"To report a bug, please also include the contents of {fn}"
    dts_print(msg, "yellow")


def env_option(key: str, default: Any = NOTSET, true_choices: List[str] = None) -> Optional[Any]:
    if default in [NOTSET, True, False]:
        # boolean options
        true_choices = true_choices or ["1", "true", "yes"]
        default = "1" if default is True else "0"
        return os.environ.get(key, default).lower().strip() in true_choices
    else:
        # non-boolean options
        if true_choices is not None:
            raise ValueError("You cannot use 'default' and 'true_choices' at the same time.")
        return os.environ.get(key, default)
