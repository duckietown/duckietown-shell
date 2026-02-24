# This replaces the old default __init__ file for the Duckietown Shell commands
#
# Maintainer: Andrea F. Daniele
import copy
import importlib
import importlib.util
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


def _preload_command_set_packages(command_set: CommandSet, module_parts: List[str]) -> None:
    """
    Pre-load packages from the command set to prevent Python from finding built-in modules
    with the same names (e.g., 'code', 'devel') or missing dependencies (e.g., 'utils').

    Args:
        command_set: The command set containing the packages
        module_parts: List of module name parts (e.g., ['code', 'build'] for 'code.build')
    """
    # Pre-load utility package from command set (e.g., 'utils') that may be imported
    _util_pkg = "utils"
    _util_path = _join(command_set.path, _util_pkg)
    _util_init = _join(_util_path, "__init__.py")
    if _exists(_util_init) and _util_pkg not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            _util_pkg,
            _util_init,
            submodule_search_locations=[_util_path]
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[_util_pkg] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                # Log the exception to aid debugging when utility package loading fails
                logger.exception(
                    f"Failed to preload utility package '{_util_pkg}' from '{_util_path}'. Removing it from "
                    "sys.modules."
                )
                # If loading fails, remove from sys.modules
                if _util_pkg in sys.modules:
                    del sys.modules[_util_pkg]

    # Pre-load parent packages from command set to prevent Python from finding built-in modules
    for idx in range(1, len(module_parts) + 1):
        _parent_name = ".".join(module_parts[:idx])
        _parent_path = _join(command_set.path, *module_parts[:idx])
        _parent_init = _join(_parent_path, "__init__.py")

        # Check if module is already loaded
        if _parent_name in sys.modules:
            mod = sys.modules.get(_parent_name)
            # Check if it's from our command set
            if mod is not None and hasattr(mod, "__path__") and any(command_set.path in str(p) for p in mod.__path__):
                # It's ours, keep it
                continue
            else:
                # It's a conflicting module, remove it
                if DTShellConstants.VERBOSE:
                    module_file = getattr(mod, "__file__")
                    logger.debug(f"Removing conflicting module '{_parent_name}' ({module_file})")
                del sys.modules[_parent_name]

        # Explicitly load our package if it exists
        if not _exists(_parent_init):
            continue
        spec = importlib.util.spec_from_file_location(
            _parent_name,
            _parent_init,
            submodule_search_locations=[_parent_path]
        )
        if not spec or not spec.loader:
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[_parent_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            # If loading fails, remove from sys.modules
            if _parent_name in sys.modules:
                del sys.modules[_parent_name]
            raise


def import_commandset_configuration(command_set: CommandSet) -> Type[DTCommandSetConfigurationAbs]:
    # constants
    _configuration_file = _join(command_set.path, "__command_set__", "configuration.py")
    # import command set configuration
    if _exists(_configuration_file):
        if DTShellConstants.VERBOSE:
            logger.debug(f"Importing configuration for command set '{command_set.name}' from "
                         f"'{_configuration_file}'")
        # use a unique module name to avoid caching issues between command sets
        _module_name: str = f"__command_set_config_{command_set.name}__"
        # we temporarily add the path to the command set to PYTHONPATH
        old: List[str] = copy.deepcopy(sys.path)
        sys.path.insert(0, os.path.abspath(command_set.path))
        try:
            # load the configuration module from the specific file
            spec = importlib.util.spec_from_file_location(_module_name, _configuration_file)
            if spec is None or spec.loader is None:
                msg = f"Cannot load command set configuration module from {_configuration_file}"
                raise CommandsLoadingException(msg)
            configuration = importlib.util.module_from_spec(spec)
            sys.modules[_module_name] = configuration
            spec.loader.exec_module(configuration)
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
        # populate path on default configuration as well
        default_commandset_configuration.DTCommandSetConfiguration.path = command_set.path
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

            # Pre-load packages to prevent conflicts with built-in modules and ensure dependencies
            _parts = _command_sel.split('.')
            _preload_command_set_packages(command_set, _parts)

            configuration = importlib.import_module(_configuration_sel)
        except ShellNeedsUpdate as e:
            logger.warning(
                f"Command '{_command_sel}' was not loaded because the shell needs to be "
                f"updated. Current version is {e.current_version}, required version is "
                f"{e.version_needed}"
            )
            return default_command_configuration.DTCommandConfiguration
        except ModuleNotFoundError as e:
            logger.warning(
                f"Command configuration '{_command_sel}' could not be loaded due to missing dependency: {e}. "
                f"Using default configuration."
            )
            return default_command_configuration.DTCommandConfiguration
        except Exception as e:
            logger.warning(
                f"Command configuration '{_command_sel}' could not be loaded: {e}. "
                f"Using default configuration."
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
