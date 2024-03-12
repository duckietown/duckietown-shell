import logging
from typing import Optional, Sequence

import termcolor

from .utils import dark_yellow

__all__ = ["dts_print", "setup_logging_color"]


def dts_print(msg: str, color: Optional[str] = None, attrs: Sequence[str] = ()) -> None:
    """
    Prints a message to the user.
    """
    msg = msg.strip(" ")  # remove space
    print("")  # always separate
    lines = msg.split("\n")
    prefix = "dts : "
    filler = "    : "
    # filler = ' ' * len(prefix)

    for i, line in enumerate(lines):
        f = prefix if i == 0 else filler
        on_color = None
        line = line.replace("\t", " " * 4)
        line = termcolor.colored(line, color, on_color, list(attrs))
        s = "%s %s" % (dark_yellow(f), line)
        print(s)


def add_coloring_to_emit_ansi(fn):
    # add methods we need to the class
    def new(*args):
        levelno = args[1].levelno
        if levelno >= 50:
            color = "\x1b[31m"  # red
        elif levelno >= 40:
            color = "\x1b[31m"  # red
        elif levelno >= 30:
            color = "\x1b[33m"  # yellow
        elif levelno >= 20:
            color = "\x1b[32m"  # green
        elif levelno >= 10:
            color = "\x1b[35m"  # pink
        else:
            color = "\x1b[0m"  # normal

        msg = str(args[1].msg)

        lines = msg.split("\n")

        def color_line(line):
            return "%s%s%s" % (color, line, "\x1b[0m")  # normal

        lines = list(map(color_line, lines))

        args[1].msg = "\n".join(lines)
        return fn(*args)

    return new


def setup_logging_color():
    import platform

    if platform.system() != "Windows":
        emit2 = add_coloring_to_emit_ansi(logging.StreamHandler.emit)
        logging.StreamHandler.emit = emit2
