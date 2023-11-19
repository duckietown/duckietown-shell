import argparse
from typing import Optional, List, Set

import questionary
from questionary import Choice

from dt_shell import DTCommandAbs, DTShell, UserAborted, UserError, dtslogger
from dt_shell.utils import cli_style


class DTCommand(DTCommandAbs):
    help = 'Switch to a different profile'

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # parse arguments
        parsed: argparse.Namespace = DTCommand.parser.parse_args(args)
        # get list of existing profiles
        profiles: Set[str] = set(shell.profiles.keys())
        # ask the user what profile to switch to if none is given
        new_profile: str
        if parsed.profile is not None:
            # make sure the given profile exists
            if parsed.profile not in profiles:
                raise UserError(f"Profile '{parsed.profile}' does not exist")
            new_profile = parsed.profile
        else:
            dtslogger.info("Choose the profile you want to switch to")
            distros: List[Choice] = []
            for profile in profiles:
                extras: str = "" if profile != shell.profile.name else f"(current)"
                label = [
                    ("class:choice", profile),
                    ("class:disabled", f" {extras}")
                ]
                choice: Choice = Choice(title=label, value=profile)
                distros.append(choice)
            # let the user choose the profile
            new_profile: Optional[str] = questionary.select(
                "Choose a profile:", choices=distros, style=cli_style).unsafe_ask()
            if new_profile is None:
                raise UserAborted()

        # same profile?
        if new_profile == shell.profile.name:
            dtslogger.info(f"Already on profile '{new_profile}'")
            return
        # switch profile
        dtslogger.info(f"Switching to profile '{new_profile}'...")
        # set the new profile as the profile to load at the next launch
        shell.settings.profile = new_profile
        dtslogger.info(f"Active profile is now set to '{new_profile}'")

    @staticmethod
    def complete(shell: DTShell, word: str, line: str) -> List[str]:
        return []
