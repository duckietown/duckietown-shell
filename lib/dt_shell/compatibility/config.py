import copy
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class ShellConfig:
    token_dt1: Optional[str]  # key
    docker_username: Optional[str]
    docker_password: Optional[str]
    duckietown_version: Optional[str]  # ente, daffy, master19, ...
    docker_credentials: Dict[str, Dict[str, str]]  # username, secret


_instance: Optional[ShellConfig] = None


def get_shell_config_default() -> ShellConfig:
    return ShellConfig(
        token_dt1=None,
        docker_username=None,
        docker_password=None,
        duckietown_version=None,
        docker_credentials={},
    )


def read_shell_config(shell) -> ShellConfig:
    global _instance
    if _instance is None:
        docker_credentials: Dict[str, dict] = {
            registry: copy.deepcopy(credentials)
            for registry, credentials in shell.profile.secrets.docker_credentials.items()
        }
        # rename password -> secret
        for credentials in docker_credentials.values():
            credentials["secret"] = credentials.pop("password")
        # package as ShellConfig
        _instance = ShellConfig(
            token_dt1=shell.profile.secrets.dt1_token,
            docker_username=None,
            docker_password=None,
            duckietown_version=shell.profile.name,
            docker_credentials=docker_credentials,
        )
    return _instance
