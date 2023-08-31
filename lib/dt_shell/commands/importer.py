# This replaces the old default __init__ file for the Duckietown Shell commands
#
# Maintainer: Andrea F. Daniele
import importlib
import os.path
from os.path import (
    exists as _exists,
    dirname as _dirname,
    relpath as _relpath,
    join as _join,
)
from typing import Type

from .. import dtslogger
from .commands import default_command_configuration, failed_to_load_command, DTCommandConfigurationAbs, \
    DTCommandAbs, DTCommandPlaceholder
from ..exceptions import ShellNeedsUpdate, CommandsLoadingException


def import_configuration(fpath: str) -> Type[DTCommandConfigurationAbs]:
    # TODO: this is not efficient
    import __shell_commands_root__
    # constants
    _command_dir = _dirname(fpath)
    _configuration_file = _join(_command_dir, "configuration.py")
    # import command configuration
    if _exists(_configuration_file):
        _command_sel: str = _relpath(_command_dir, __shell_commands_root__.path).strip("/").replace("/", ".")
        _configuration_sel: str = f"{_command_sel}.configuration"
        try:
            dtslogger.debug(f"Importing configuration for command '{_command_sel}' from "
                            f"'{_configuration_file}'")
            configuration = importlib.import_module(_configuration_sel)
        except ShellNeedsUpdate as e:
            dtslogger.warning(
                f"Command '{_command_sel}' was not loaded because the shell needs to be "
                f"updated. Current version is {e.current_version}, required version is "
                f"{e.version_needed}"
            )
            return default_command_configuration.DTCommandConfiguration

        DTCommandConfiguration = configuration.DTCommandConfiguration
        if not issubclass(DTCommandConfiguration.__class__, DTCommandConfigurationAbs.__class__):
            msg = f"Cannot load command configuration class in {_configuration_file}, the class " \
                  f"'DTCommandConfiguration' must extend the class 'DTCommandConfigurationAbs'"
            raise CommandsLoadingException(msg)

        return DTCommandConfiguration
    else:
        return default_command_configuration.DTCommandConfiguration


def import_command(configuration: Type[DTCommandConfigurationAbs], fpath: str) -> Type[DTCommandAbs]:
    # TODO: this is not efficient
    import __shell_commands_root__
    # we always start from an __init__.py file
    if os.path.isdir(fpath):
        fpath = os.path.join(fpath, "__init__.py")
    # constants
    _command_dir = _dirname(fpath) if os.path.isfile(fpath) else fpath
    _command_file = _join(_command_dir, "command.py")
    # import current command
    if _exists(_command_file):
        _command_sel: str = _relpath(_command_dir, __shell_commands_root__.path).strip("/").replace("/", ".")
        _command_sel: str = f"{_command_sel}.command"
        try:
            dtslogger.debug(f"Importing command '{_command_sel}' from '{_dirname(fpath)}/'")
            command = importlib.import_module(_command_sel)
        except ShellNeedsUpdate as e:
            dtslogger.warning(
                f"Command '{_command_sel}' was not loaded because the shell needs to be "
                f"updated. Current version is {e.current_version}, required version is "
                f"{e.version_needed}"
            )
            return failed_to_load_command.DTCommand

        DTCommand = command.DTCommand        # handle wrong class
        if not issubclass(DTCommand.__class__, DTCommandAbs.__class__):
            msg = f"Cannot load command class in {_command_file}, the class " \
                  f"'DTCommand' must extend the class 'DTCommandAbs'"
            raise CommandsLoadingException(msg)
        return DTCommand
    else:
        return failed_to_load_command.DTCommand
