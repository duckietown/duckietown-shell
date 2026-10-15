import argparse
from typing import List, Optional

from dt_shell import UserError
from dt_shell.integrity import is_developer_mode, is_release_build


def run_developer_command(
    subcommand: str, args: List[str], parser: Optional[argparse.ArgumentParser]
) -> None:
    if parser is None:
        raise UserError("Developer-command configuration is unavailable. Reinstall the official DTS package.")
    parser.parse_args(args)
    if not is_release_build() and not is_developer_mode():
        raise UserError(
            "Developer grants are managed by the official native DTS installation. "
            "The explicit Python source-development workflow is not an authenticated official runtime."
        )
    from dt_shell_release import (
        ReleaseIntegrityError,
        manage_developer_authorization,
    )

    try:
        manage_developer_authorization([subcommand])
    except ReleaseIntegrityError as error:
        raise UserError(str(error)) from error
