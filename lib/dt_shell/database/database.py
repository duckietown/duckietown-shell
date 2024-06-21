import copy
import os.path
from abc import abstractmethod, ABC
from contextlib import contextmanager
from threading import Semaphore
from typing import Union, TypeVar, Generic, Tuple, Optional, Dict, Iterator, ContextManager

import yaml
from filelock import FileLock, Timeout

from ..exceptions import ConfigInvalid
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
        self._ephemeral: dict = {}
        self._lock: Semaphore = Semaphore()
        self._atomic: FileLock = FileLock(f"{self.yaml}.lock", timeout=10)
        self._in_memory: bool = False
        # ---
        raise RuntimeError(f'Call {self.__class__.__name__}.open() instead')

    @classmethod
    def open(cls, name: str, location: Optional[str] = DATABASES_DIR, readonly: bool = False,
             init_args: dict = None) -> 'DTShellDatabase':
        key = (location, name)
        if key not in cls._instances:
            # noinspection PyArgumentList
            inst = cls.__new__(cls, **(init_args or {}))
            cls._instances[key] = inst
            # populate instance fields
            inst._name = name
            inst._location = location
            inst._readonly = readonly or cls.global_readonly
            inst._data = {}
            inst._ephemeral = {}
            inst._lock = Semaphore()
            inst._atomic = FileLock(f"{inst.yaml}.lock", timeout=10)
            inst._in_memory = False
            # set custom init args
            for k, v in (init_args or {}).items():
                setattr(inst, k, v)
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

    @contextmanager
    def in_memory(self) -> ContextManager:
        # code to acquire resource
        self._in_memory = True
        try:
            yield self
        finally:
            # code to release resource
            self._in_memory = False

    @property
    def size(self) -> int:
        return len(self._data)

    def contains(self, key: Key) -> bool:
        key = self._key(key)
        return key in self._data

    def get(self, key: Key, default: Optional[T] = NOTSET) -> T:
        key = self._key(key)
        # in memory?
        if key in self._ephemeral:
            return self._ephemeral[key]
        # read from persistent data
        try:
            return self._data[key]
        except KeyError:
            if default is NOTSET:
                raise DTShellDatabase.NotFound(f"Key '{key}' not found in database.")
            else:
                return default

    def delete(self, key: Key):
        key = self._key(key)
        # in memory?
        self._ephemeral.pop(key, None)
        # persistent data
        with self._lock:
            self._data.pop(key, None)
        self._write()

    def set(self, key: Key, value: T):
        key = self._key(key)
        with self._lock:
            # in memory?
            if self._in_memory:
                self._ephemeral[key] = value
            else:
                self._data[key] = value
                self._ephemeral.pop(key, None)
            # ---
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
            try:
                with self._atomic:
                    with open(self.yaml, "rt") as fin:
                        content = yaml.safe_load(fin)
            except Timeout:
                raise TimeoutError(f"Could not acquire lock for '{self.yaml}'. "
                                   f"If this happens often, delete the file {self.yaml}.lock")
            # populate internal state
            try:
                self._data = content["data"]
            except KeyError:
                raise ConfigInvalid(f"Database file '{self.yaml}' is corrupted. Missing 'data' key. Check with "
                                    f"technical support if it is ok to delete this file.")
            except TypeError:
                raise ConfigInvalid(f"Database file '{self.yaml}' is corrupted. Check with "
                                    f"technical support if it is ok to delete this file.")

    def _write(self):
        # skip writing to disk if in read-only mode
        if self._readonly:
            return
        # complete data with other metadata
        with self._lock:
            content = {**EMPTY_DB, "data": {**self._data}}
            # write to disk
            try:
                with self._atomic:
                    with open(self.yaml, "wt") as fout:
                        yaml.safe_dump(content, fout, indent=4)
            except Timeout:
                raise TimeoutError(f"Could not acquire lock for '{self.yaml}'. "
                                   f"If this happens often, delete the file {self.yaml}.lock")

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
