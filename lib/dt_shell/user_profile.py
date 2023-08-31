import dataclasses
import os.path
from typing import Optional

from . import dtslogger
from .utils import safe_pathname
from .database.database import DTShellDatabase

DEFAULT_PROFILES_DIR = os.path.expanduser("~/.duckietown/shell/profiles")


@dataclasses.dataclass
class UserProfile:
    name: str
    path: Optional[str] = None

    def __post_init__(self):
        if self.path is None:
            profiles_dir: str = os.environ.get("DTSHELL_PROFILES", DEFAULT_PROFILES_DIR)
            if profiles_dir != DEFAULT_PROFILES_DIR:
                dtslogger.info(f"Loading profiles from '{profiles_dir}' as prescribed by the environment "
                               f"variable DTSHELL_PROFILES.")
            safe_name: str = safe_pathname(self.name)
            self.path = os.path.join(profiles_dir, safe_name)
        #

    @property
    def _databases_location(self) -> str:
        return os.path.join(self.path, "databases")

    def database(self, name: str) -> DTShellDatabase:
        return DTShellDatabase.open(name, location=self._databases_location)

    def _ensure_path(self):
        if not os.path.exists(self.path):
            os.makedirs(self.path)
