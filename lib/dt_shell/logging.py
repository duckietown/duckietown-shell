from typing import Optional, Sequence

import termcolor

from .utils import dark_yellow

__all__ = ["dts_print"]


def dts_print(msg: str, color: Optional[str] = None, attrs: Sequence[str] = ()) -> None:
    """
        Prints a message to the user.
    """
    msg = msg.strip()  # remove space
    print("")  # always separate
    lines = msg.split("\n")
    prefix = "dts : "
    filler = "    : "
    # filler = ' ' * len(prefix)

    for i, line in enumerate(lines):
        f = prefix if i == 0 else filler
        line = termcolor.colored(line, color=color, attrs=list(attrs))
        s = "%s %s" % (dark_yellow(f), line)
        print(s)
