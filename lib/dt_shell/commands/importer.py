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

from dt_shell.constants import DTShellConstants

from .. import logger
from ..exceptions import ShellNeedsUpdate, CommandsLoadingException
from .commands import default_command_configuration, failed_to_load_command, DTCommandConfigurationAbs, \
    DTCommandAbs, CommandSet, DTCommandSetConfigurationAbs, default_commandset_configuration


def import_commandset_configuration(command_set: CommandSet) -> Type[DTCommandSetConfigurationAbs]:
    # constants
    _configuration_file = _join(command_set.path, "__command_set__", "configuration.py")
    # import command set configuration
    if _exists(_configuration_file):
        if DTShellConstants.VERBOSE:
            logger.debug(f"Importing configuration for command set '{command_set.name}' from "
                         f"'{_configuration_file}'")
        _configuration_sel: str = "__command_set__.configuration"
        # we temporarily add the path to the command set to PYTHONPATH
        old: List[str] = copy.deepcopy(sys.path)
        sys.path.insert(0, os.path.abspath(command_set.path))
        try:
            # import/refresh the configuration module
            configuration = importlib.import_module(_configuration_sel)
            if configuration.__file__ != _configuration_file:
                importlib.reload(configuration)
            # make sure we got the right one
            assert configuration.__file__ == _configuration_file
        finally:
            # restore PYTHONPATH
            sys.path = old

        DTCommandSetConfiguration: Type[DTCommandSetConfigurationAbs] = \
            configuration.DTCommandSetConfiguration
        if not issubclass(DTCommandSetConfiguration.__class__, DTCommandSetConfigurationAbs.__class__):
            msg = f"Cannot load command set configuration class in {_configuration_file}, the class " \
                  f"'DTCommandSetConfiguration' must extend the class 'DTCommandSetConfigurationAbs'"
            raise CommandsLoadingException(msg)
        # populate path
        DTCommandSetConfiguration.path = command_set.path

        return DTCommandSetConfiguration
    else:
        return default_commandset_configuration.DTCommandSetConfiguration


def import_commandset_init(command_set: CommandSet):
    # constants
    _init_file = _join(command_set.path, "__command_set__", "init.py")
    # skip if there is no init file for this command set
    if not _exists(_init_file):
        return
    # import command set init
    if DTShellConstants.VERBOSE:
        logger.debug(f"Executing init script for command set '{command_set.name}' from '{_init_file}'")
    _init_sel: str = "__command_set__.init"
    # we temporarily add the path to the command set to PYTHONPATH
    old: List[str] = copy.deepcopy(sys.path)
    sys.path.insert(0, os.path.abspath(command_set.path))
    # import/refresh the init module
    try:
        init = importlib.import_module(_init_sel)
        if init.__file__ != _init_file:
            importlib.reload(init)
        # make sure we got the right one
        assert init.__file__ == _init_file
    finally:
        # restore PYTHONPATH
        sys.path = old


def import_configuration(command_set: CommandSet, selector: str) -> Type[DTCommandConfigurationAbs]:
    # constants
    _command_dir = command_set.command_path(selector)
    _configuration_file = _join(_command_dir, "configuration.py")
    # import command configuration
    if _exists(_configuration_file):
        _command_sel: str = _relpath(_command_dir, command_set.path).strip("/").replace("/", ".")
        _configuration_sel: str = f"{_command_sel}.configuration"
        # we temporarily add the path to the command set to PYTHONPATH
        old: List[str] = copy.deepcopy(sys.path)
        sys.path.insert(0, os.path.abspath(command_set.path))
        try:
            if DTShellConstants.VERBOSE:
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
        finally:
            # restore PYTHONPATH
            sys.path = old

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
            if DTShellConstants.VERBOSE:
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
