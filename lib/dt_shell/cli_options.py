import argparse
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .constants import ALLOWED_BRANCHES

__all__ = ["CLIOptions", "get_cli_options"]


@dataclass
class CLIOptions:
    debug: bool
    set_version: Optional[str]


def get_cli_options(args: List[str]) -> Tuple[CLIOptions, List[str]]:
    """ Returns cli options plus other arguments for the commands. """

    if args and not args[0].startswith("-"):
        return CLIOptions(debug=False, set_version=None), args
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--debug", action="store_true", default=False, help="More debug information"
    )
    parser.add_argument(
        "--set-version",
        type=str,
        default=None,
        help=f"Set Duckietown version. Use one of {ALLOWED_BRANCHES}",
    )

    parsed, others = parser.parse_known_args(args)

    return CLIOptions(debug=parsed.debug, set_version=parsed.set_version), others
