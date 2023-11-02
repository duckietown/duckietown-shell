import os.path
import shutil
from typing import Optional, List

import yaml

from dt_shell.constants import DB_MIGRATIONS, KNOWN_DISTRIBUTIONS
from dt_shell.database import DTShellDatabase
from dt_shell.profile import ShellProfile, DockerCredentials, GenericCredentials, ShellProfileSecrets

OLD_ROOT: str = os.path.expanduser("~/.dt-shell")


def read_old_config() -> Optional[dict]:
    # old config file
    config_fpath: str = os.path.join(OLD_ROOT, "config.yaml")
    if not os.path.exists(config_fpath):
        return None
    with open(config_fpath, "rt") as fin:
        return yaml.safe_load(fin.read())


def needs_migrate_distro() -> bool:
    # check migrations database
    return not _already_migrated("distro")


def needs_migrate_docker_credentials() -> bool:
    # check migrations database
    return not _already_migrated("docker_credentials")


def needs_migrate_token_dt1() -> bool:
    # check migrations database
    return not _already_migrated("token_dt1")


def needs_migrate_secrets() -> bool:
    # check migrations database
    return not _already_migrated("secrets")


def needs_migrations() -> bool:
    return needs_migrate_docker_credentials() or \
           needs_migrate_token_dt1() or \
           needs_migrate_secrets()


def mark_distro_migrated():
    _mark_migrated("distro")


def mark_docker_credentials_migrated():
    _mark_migrated("docker_credentials")


def mark_token_dt1_migrated():
    _mark_migrated("token_dt1")


def mark_secrets_migrated():
    _mark_migrated("secrets")


def mark_all_migrated():
    mark_distro_migrated()
    mark_docker_credentials_migrated()
    mark_token_dt1_migrated()
    mark_secrets_migrated()


def migrate_docker_credentials(profile) -> int:
    profile: ShellProfile
    try:
        # old config file
        config: dict = read_old_config()
        if not config:
            return 0
        # open new database
        db: DockerCredentials = profile.secrets.docker_credentials
        # migrate credentials
        docker_credentials: dict = config.get("docker_credentials", {})
        for registry, credentials in docker_credentials.items():
            db.set(
                registry,
                GenericCredentials(username=credentials["username"], password=credentials["secret"])
            )
        # return the number of credentials migrated
        return len(docker_credentials)
    finally:
        # mark as migrated
        mark_docker_credentials_migrated()


def migrate_distro(dryrun: bool = False) -> Optional[str]:
    profile: ShellProfile
    try:
        # old config file
        config: dict = read_old_config()
        if not config:
            return None
        # get distro
        distro: str = config.get("duckietown_version", None)
        known_distros: List[str] = [d.name for d in KNOWN_DISTRIBUTIONS.values()]
        if distro not in known_distros:
            return None
        # ---
        return distro
    finally:
        # mark it as migrated
        if not dryrun:
            mark_distro_migrated()


def migrate_token_dt1(profile) -> Optional[str]:
    profile: ShellProfile
    try:
        # old config file
        config: dict = read_old_config()
        if not config:
            return None
        # open new database
        db: ShellProfileSecrets = profile.secrets
        # migrate credentials
        token_dt1: str = config.get("token_dt1", None)
        if not token_dt1:
            return None
        db.dt1_token = token_dt1
        # ---
        return token_dt1
    finally:
        # mark as migrated
        mark_token_dt1_migrated()


def migrate_secrets(profile):
    profile: ShellProfile
    try:
        # secrets dirs
        old_secrets_dir: str = os.path.join(OLD_ROOT, "secrets")
        new_secrets_dir: str = os.path.join(profile.path, "secrets")
        # skip if the old profile does not have a secrets dir
        if not os.path.exists(old_secrets_dir):
            return
        # copy all files
        _copy_and_overwrite(old_secrets_dir, new_secrets_dir)
    finally:
        # mark it as migrated
        mark_secrets_migrated()


def _copy_and_overwrite(from_path: str, to_path: str):
    shutil.copytree(from_path, to_path, dirs_exist_ok=True)


def _mark_migrated(key: str):
    migrations_db: DTShellDatabase[bool] = DTShellDatabase.open(DB_MIGRATIONS)
    migrations_db.set(key, True)


def _already_migrated(key: str) -> bool:
    migrations_db: DTShellDatabase[bool] = DTShellDatabase.open(DB_MIGRATIONS)
    return migrations_db.get(key, False)
