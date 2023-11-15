import dataclasses
import os
import time
from typing import Iterator

from .constants import DB_STATISTICS_EVENTS
from .database import DTShellDatabase


@dataclasses.dataclass
class StatsEvent:
    name: str
    time: float
    payload: dict
    __db__: 'ShellProfileEventsDatabase'
    __key__: str

    def delete(self):
        self.__db__.delete(self.__key__)


class ShellProfileEventsDatabase(DTShellDatabase[dict]):

    @classmethod
    def load(cls, location: str):
        return ShellProfileEventsDatabase.open(DB_STATISTICS_EVENTS, location=location)

    @property
    def in_memory(self) -> bool:
        return os.environ.get("DTSHELL_DISABLE_STATS", "0").lower() in ["1", "yes", "true"]

    def get(self, *_, **__):
        raise NotImplementedError("Use the method ShellProfileEventsDatabase.events() instead.")

    def set(self, *_, **__):
        raise NotImplementedError("Use the method ShellProfileEventsDatabase.new() instead.")

    def events(self) -> Iterator[StatsEvent]:
        for key in self.keys():
            value: dict = super(ShellProfileEventsDatabase, self).get(key)
            yield StatsEvent(**value, __db__=self, __key__=key)

    def new(self, name: str, payload: dict = None, when: float = None) -> StatsEvent:
        now: float = time.time()
        key: str = str(now)
        value: dict = {"name": name, "time": when or now, "payload": payload or {}}
        if not self.in_memory:
            super(ShellProfileEventsDatabase, self).set(key, value)
        return StatsEvent(**value, __db__=self, __key__=key)
