# This replaces the old default __init__ file for the Duckietown Shell commands
#
# Maintainer: Andrea F. Daniele
import copy
import importlib
import os.path
import sys
from os.path import (
    exists as _exists,
    dirname as _dirname,
    relpath as _relpath,
    join as _join,
)
from typing import Type, List

from .. import logger
from .commands import default_command_configuration, failed_to_load_command, DTCommandConfigurationAbs, \
    DTCommandAbs, CommandSet, DTCommandSetConfigurationAbs, default_commandset_configuration, \
    CommandDescriptor
from ..exceptions import ShellNeedsUpdate, CommandsLoadingException


def import_commandset_configuration(command_set: CommandSet) -> Type[DTCommandSetConfigurationAbs]:
    # constants
    _configuration_file = _join(command_set.path, "__command_set__", "configuration.py")
    # import command set configuration
    if _exists(_configuration_file):
        logger.debug(f"Importing configuration for command set '{command_set.name}' from "
                     f"'{_configuration_file}'")
        _configuration_sel: str = "__command_set__.configuration"
        # we temporarily add the path to the command set to PYTHONPATH
        old: List[str] = copy.deepcopy(sys.path)
        sys.path.insert(0, os.path.abspath(command_set.path))
        # import/refresh the configuration module
        configuration = importlib.import_module(_configuration_sel)
        importlib.reload(configuration)
        # make sure we got the right one
        assert configuration.__file__ == _configuration_file
        # restore PYTHONPATH
        sys.path = old

        DTCommandSetConfiguration = configuration.DTCommandSetConfiguration
        if not issubclass(DTCommandSetConfiguration.__class__, DTCommandSetConfigurationAbs.__class__):
            msg = f"Cannot load command set configuration class in {_configuration_file}, the class " \
                  f"'DTCommandSetConfiguration' must extend the class 'DTCommandSetConfigurationAbs'"
            raise CommandsLoadingException(msg)

        return DTCommandSetConfiguration
    else:
        return default_commandset_configuration.DTCommandSetConfiguration


def import_configuration(command_set: CommandSet, command: CommandDescriptor) -> Type[DTCommandConfigurationAbs]:
    # constants
    _command_dir = _dirname(command.path)
    _configuration_file = _join(_command_dir, "configuration.py")
    # import command configuration
    if _exists(_configuration_file):
        _command_sel: str = _relpath(_command_dir, command_set.path).strip("/").replace("/", ".")
        _configuration_sel: str = f"{_command_sel}.configuration"
        try:
            logger.debug(f"Importing configuration for command '{_command_sel}' from "
                         f"'{_configuration_file}'")
            configuration = importlib.import_module(_configuration_sel)
        except ShellNeedsUpdate as e:
            logger.warning(
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


def import_command(command_set: CommandSet, fpath: str) -> Type[DTCommandAbs]:
    # we always start from an __init__.py file
    if os.path.isdir(fpath):
        fpath = os.path.join(fpath, "__init__.py")
    # constants
    _command_dir = _dirname(fpath) if os.path.isfile(fpath) else fpath
    _command_file = _join(_command_dir, "command.py")
    # import current command
    if _exists(_command_file):
        _command_sel: str = _relpath(_command_dir, command_set.path).strip("/").replace("/", ".")
        _command_sel: str = f"{_command_sel}.command"
        try:
            logger.debug(f"Importing command '{_command_sel}' from '{_dirname(fpath)}/'")
            command = importlib.import_module(_command_sel)
        except ShellNeedsUpdate as e:
            logger.warning(
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
