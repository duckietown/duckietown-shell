import argparse
import logging
from typing import Optional, List, Set

import questionary
from questionary import Choice

from dt_shell import DTCommandAbs, DTShell, UserAborted, UserError, dtslogger
from dt_shell.constants import KNOWN_DISTRIBUTIONS, SUGGESTED_DISTRIBUTION, EMBEDDED_COMMAND_SET_NAME
from dt_shell.profile import ShellProfile
from dt_shell.utils import cli_style
from dt_shell_cli import logger


class DTCommand(DTCommandAbs):
    help = 'Create new profile'

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # parse arguments
        parsed: argparse.Namespace = DTCommand.parser.parse_args(args)
        # get list of existing profiles
        profiles: Set[str] = set(shell.profiles.keys())
        # ask the user for a distribution to use
        dtslogger.info("In order to make a new profile, you need to choose a distribution first.")
        distros: List[Choice] = []
        for distro in KNOWN_DISTRIBUTIONS.values():
            # filter by staging VS production
            if parsed.staging != distro.staging:
                continue
            # only show stable distributions
            if not distro.stable and not parsed.unstable:
                continue
            # create questionnaire
            extras: str = "" if distro.branch not in profiles else f"(profile already exists)"
            eol: str = "" if distro.end_of_life is None else f"(end of life: {distro.end_of_life_fmt})"
            label = [
                ("class:choice", distro.branch),
                ("class:disabled", f"    {eol}"),
                ("class:disabled", f" {extras}")
            ]
            choice: Choice = Choice(title=label, value=distro.branch)
            if distro.branch.startswith(SUGGESTED_DISTRIBUTION) and distro.branch not in profiles:
                distros.insert(0, choice)
            else:
                distros.append(choice)
        # let the user choose the distro
        new_profile: Optional[str] = questionary.select(
            "Choose a distribution:", choices=distros, style=cli_style).unsafe_ask()
        if new_profile is None:
            raise UserAborted()
        # let's make sure the user did not choose a distro for which a profile already exists
        if new_profile in profiles:
            raise UserError(f"A profile for the distribution '{new_profile}' already exists. "
                            f"Use the following command to switch profile."
                            f"\n\n\n\t\tdts profile switch {new_profile}\n\n")
        # make a new profile
        dtslogger.info(f"Setting up a new profile '{new_profile}'...")
        profile: ShellProfile = ShellProfile(name=new_profile, _distro=new_profile)
        # set the new profile as the profile to load at the next launch
        shell.settings.profile = new_profile
        # configure profile
        profile.configure()
        # download command sets
        logger.setLevel(logging.INFO)
        for cs in profile.command_sets:
            if cs.name == EMBEDDED_COMMAND_SET_NAME:
                continue
            if cs.leave_alone:
                continue
            # update command set
            cs.update()
        logger.setLevel(logging.WARNING)

    @staticmethod
    def complete(shell: DTShell, word: str, line: str) -> List[str]:
        return []
