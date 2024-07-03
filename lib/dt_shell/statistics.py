import dataclasses
import os
import time
from typing import Iterator, Optional

from dt_shell_cli import logger
from .constants import DB_STATISTICS_EVENTS
from .database import DTShellDatabase
from .utils import safe_pathname


@dataclasses.dataclass
class StatsEvent:
    name: str
    time: float
    payload: dict
    __db__: 'ShellProfileEventsDatabase'
    __key__: str
    # optional
    format: int = 1
    labels: Optional[dict] = None

    @property
    def time_millis(self) -> int:
        return int(self.time * 1000)

    def delete(self):
        self.__db__.delete(self.__key__)


class ShellProfileEventsDatabase(DTShellDatabase[dict]):

    @classmethod
    def load(cls, location: str):
        return ShellProfileEventsDatabase.open(DB_STATISTICS_EVENTS, location=location)

    @classmethod
    def reset(cls, location: str):
        # remove file
        try:
            yaml_fpath: str = os.path.abspath(os.path.join(location, f"{safe_pathname(DB_STATISTICS_EVENTS)}.yaml"))
            logger.warning(f"Removing file '{yaml_fpath}'")
            os.remove(yaml_fpath)
        except FileNotFoundError:
            pass
        # open new instance (will recreate the file)
        return ShellProfileEventsDatabase.open(DB_STATISTICS_EVENTS, location=location)

    @property
    def in_memory(self) -> bool:
        return os.environ.get("DTSHELL_DISABLE_STATS", "0").lower() in ["1", "yes", "true"]

    def get(self, *_, **__):
        raise NotImplementedError("Use the method ShellProfileEventsDatabase.events() instead.")

    def set(self, *_, **__):
        raise NotImplementedError("Use the method ShellProfileEventsDatabase.new() instead.")

    def events(self) -> Iterator[StatsEvent]:
        for key in list(self.keys()):
            value: dict = super(ShellProfileEventsDatabase, self).get(key)
            try:
                yield StatsEvent(**value, __db__=self, __key__=key)
            except TypeError:
                self.delete(key)

    def new(self, name: str, payload: dict = None, when: float = None, format: int = 1,
            labels: dict = None) -> StatsEvent:
        now: float = time.time()
        key: str = str(now)
        value: dict = {
            "name": name,
            "time": when or now,
            "payload": payload or {},
            "format": format,
            "labels": labels
        }
        if not self.in_memory:
            super(ShellProfileEventsDatabase, self).set(key, value)
        return StatsEvent(**value, __db__=self, __key__=key)
