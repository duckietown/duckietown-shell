import argparse
from typing import Optional, Set

from dt_shell import DTCommandAbs, DTShell
from dt_shell.constants import Distro, KNOWN_DISTRIBUTIONS
from dt_shell.profile import ShellProfile
from utils.table_utils import format_matrix


class DTCommand(DTCommandAbs):
    help = 'List all known profiles'

    @staticmethod
    def command(shell: DTShell, args):
        # get list of existing profiles
        profiles: Set[str] = set(shell.profiles.keys())
        # make a table
        header = ["Distribution", "Staging"]
        data = []
        for profile_name in sorted(profiles):
            profile: ShellProfile = ShellProfile(profile_name, readonly=True)
            # find distro
            distro: Optional[Distro] = None
            for d in KNOWN_DISTRIBUTIONS:
                if d.name == profile.distro:
                    distro = d
                    break
            # add to table
            data.append([
                profile_name,
                profile.distro,
                ("Yes" if distro.staging else "No") if distro else "NA"
            ])
        # render table
        print()
        print(format_matrix(header, data, "{:^{}}", "{:<{}}", "{:>{}}", "\n", " | "))
        print()

    @staticmethod
    def complete(shell, word, line):
        return []
