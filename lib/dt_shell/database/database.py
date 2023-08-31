import os.path
from abc import abstractmethod, ABC
from threading import Semaphore
from typing import Union, TypeVar, Generic, Tuple, Optional, Dict

import yaml

from dt_shell.utils import safe_pathname


T = TypeVar('T')
SerializedValue = Union[int, float, str, bytes, dict, list]
Key = Union[str, Tuple[str]]


DEFAULT_DATABASES_DIR = os.path.expanduser("~/.duckietown/shell/databases/")
DATABASES_DIR = os.environ.get("DTSHELL_DATABASES", DEFAULT_DATABASES_DIR)

EMPTY_DB = {
    "version": 1,
    "data": {}
}


class DTSerializable(ABC):

    @abstractmethod
    def dump(self) -> SerializedValue:
        pass

    @classmethod
    def load(cls, v: SerializedValue) -> 'DTSerializable':
        pass


NOTSET = object()
NATURALLY_SERIALIZABLE = (int, float, str, bytes, dict, list)
SerializableValue = Union[SerializedValue, DTSerializable]
SerializableTypes = (SerializedValue, *NATURALLY_SERIALIZABLE)


class DTShellDatabase(Generic[T]):

    _instances: Dict[str, 'DTShellDatabase'] = {}

    class NotFound(KeyError):
        pass

    def __init__(self):
        self._name: str = ""
        self._location: str = ""
        self._data: dict = {}
        self._lock: Semaphore = Semaphore()
        # ---
        raise RuntimeError('Call DTShellDatabase.open() instead')

    @classmethod
    def open(cls, name: str, location: Optional[str] = DATABASES_DIR):
        if name not in cls._instances:
            inst = cls.__new__(cls)
            cls._instances[name] = inst
            # populate instance fields
            inst._name = name
            inst._location = location
            inst._data = {}
            inst._lock = Semaphore()
            # load DB from disk
            inst._load()
        # ---
        return cls._instances[name]

    @property
    def name(self) -> str:
        return self._name

    @property
    def yaml(self) -> str:
        return self._ensure_dir(os.path.join(self._location, f"{safe_pathname(self._name)}.yaml"))

    # @property
    # def filelock(self) -> str:
    #     return self._ensure_dir(os.path.join(DATABASES_DIR, f"{safe_pathname(self._name)}.yaml.lock"))

    def set(self, key: Key, value: SerializableValue):
        key = self._key(key)
        with self._lock:
            self._data[key] = value
        self._write()

    def get(self, key: Key, default: Optional[SerializableValue] = NOTSET) -> SerializableValue:
        key = self._key(key)
        try:
            return self._data[key]
        except KeyError:
            if default is NOTSET:
                raise DTShellDatabase.NotFound(f"Key '{key}' not found in database.")
            else:
                return default

    def _load(self):
        if not os.path.exists(self.yaml):
            self._write()
        with open(self.yaml, "rt") as fin:
            content = yaml.safe_load(fin)
        self._data = content["data"]

    def _write(self):
        with self._lock:
            content = {**EMPTY_DB, "data": {**self._data}}
        with open(self.yaml, "wt") as fout:
            yaml.safe_dump(content, fout, indent=4)

    @staticmethod
    def _serialize(v: object) -> SerializedValue:
        if not isinstance(v, SerializableTypes):
            raise ValueError(f"Object of type '{str(type(v))}' is not serializable. Supported types are: "
                             f"{[c.__name__ for c in SerializableTypes]}")
        if isinstance(v, NATURALLY_SERIALIZABLE):
            return v
        if isinstance(v, DTSerializable):
            return v.dump()

    @staticmethod
    def _ensure_dir(f: str) -> str:
        f = os.path.abspath(f)
        os.makedirs(os.path.dirname(f), exist_ok=True)
        return f

    @staticmethod
    def _key(k: Key) -> tuple:
        return k if isinstance(k, tuple) else (k,)
