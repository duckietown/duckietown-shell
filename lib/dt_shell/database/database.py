import copy
import os.path
from abc import abstractmethod, ABC
from threading import Semaphore
from typing import Union, TypeVar, Generic, Tuple, Optional, Dict, Iterator

import yaml

from ..utils import safe_pathname


SerializedValue = Union[int, float, str, bytes, dict, list]
T = TypeVar('T', bound=SerializedValue)
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
    @abstractmethod
    def load(cls, v: SerializedValue) -> 'DTSerializable':
        pass


NOTSET = object()
NATURALLY_SERIALIZABLE = (int, float, str, bytes, dict, list)
SerializableValue = Union[SerializedValue, DTSerializable]
SerializableTypes = (SerializedValue, *NATURALLY_SERIALIZABLE)


class DTShellDatabase(Generic[T]):

    _instances: Dict[Tuple[str, str], 'DTShellDatabase'] = {}
    global_readonly: bool = False

    class NotFound(KeyError):
        pass

    def __init__(self):
        self._name: str = ""
        self._location: str = ""
        self._readonly: bool = False
        self._data: dict = {}
        self._lock: Semaphore = Semaphore()
        # ---
        raise RuntimeError(f'Call {self.__class__.__name__}.open() instead')

    @classmethod
    def open(cls, name: str, location: Optional[str] = DATABASES_DIR, readonly: bool = False):
        key = (location, name)
        if key not in cls._instances:
            inst = cls.__new__(cls)
            cls._instances[key] = inst
            # populate instance fields
            inst._name = name
            inst._location = location
            inst._readonly = readonly or cls.global_readonly
            inst._data = {}
            inst._lock = Semaphore()
            # load DB from disk
            inst._load()
        # ---
        return cls._instances[key]

    @property
    def name(self) -> str:
        return self._name

    @property
    def yaml(self) -> str:
        yaml_fpath: str = os.path.abspath(os.path.join(self._location, f"{safe_pathname(self._name)}.yaml"))
        # make destination if it does not exist
        if not self._readonly:
            self._ensure_dir(yaml_fpath)
        # ---
        return yaml_fpath

    def contains(self, key: Key) -> bool:
        key = self._key(key)
        return key in self._data

    def get(self, key: Key, default: Optional[T] = NOTSET) -> T:
        key = self._key(key)
        try:
            return self._data[key]
        except KeyError:
            if default is NOTSET:
                raise DTShellDatabase.NotFound(f"Key '{key}' not found in database.")
            else:
                return default

    def delete(self, key: Key):
        key = self._key(key)
        with self._lock:
            self._data.pop(key, None)
        self._write()

    def set(self, key: Key, value: T):
        key = self._key(key)
        with self._lock:
            self._data[key] = value
        self._write()

    def keys(self) -> Iterator[Key]:
        with self._lock:
            data: dict = copy.copy(self._data)
        return iter(data.keys())

    def values(self) -> Iterator[T]:
        with self._lock:
            data: dict = copy.copy(self._data)
        return iter(data.values())

    def items(self) -> Iterator[Tuple[Key, T]]:
        with self._lock:
            data: dict = copy.copy(self._data)
        return iter(data.items())

    def clear(self):
        """
        Removes all the records from the database.
        """
        self._data.clear()
        self._write()

    def update(self, d: dict):
        """
        Update this database with the records from the given database.
        """
        self._data.update(d)
        self._write()

    def _load(self):
        if not self._readonly:
            # make files if they don't exist
            if not os.path.exists(self.yaml):
                self._write()
        # check if the file exists
        exists: bool = os.path.exists(self.yaml) and os.path.isfile(self.yaml)
        # read from disk
        if exists:
            with open(self.yaml, "rt") as fin:
                content = yaml.safe_load(fin)
            # populate internal state
            self._data = content["data"]

    def _write(self):
        # skip writing to disk if in read-only mode
        if self._readonly:
            return
        # complete data with other metadata
        with self._lock:
            content = {**EMPTY_DB, "data": {**self._data}}
            # write to disk
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
    def _ensure_dir(f: str):
        os.makedirs(os.path.dirname(f), exist_ok=True)

    @staticmethod
    def _key(k: Key) -> str:
        return k
