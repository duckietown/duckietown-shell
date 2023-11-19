from typing import List

import yaml

from dt_shell import __version__, DTCommandAbs, DTShell


class DTCommand(DTCommandAbs):
    help = "Prints out the version of the shell and returns."

    @staticmethod
    def command(shell: DTShell, args: List[str]):
        # noinspection PyDictCreation
        versions: dict = {}
        # shell version
        versions["shell"] = f"v{__version__}"
        # command sets
        for cs in shell.command_sets:
            command_set_versions: dict = versions.get("command sets", {})
            head_version, closest_version = cs.version, cs.closest_version
            # if we have a HEAD version, we use that one
            if head_version:
                command_set_versions[cs.name] = f"v{head_version}"
            # revert to the closest tag otherwise
            elif closest_version:
                command_set_versions[cs.name] = f"devel (closest: {closest_version})"
            else:
                command_set_versions[cs.name] = "NA"

            versions["command sets"] = command_set_versions
        # print versions
        print()
        print(yaml.safe_dump(versions, sort_keys=False).replace("'", ""))
