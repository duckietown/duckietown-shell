from abc import abstractmethod
from threading import Thread

import dt_shell
from dt_shell_cli import logger
from .constants import DTShellConstants
from .shell import Event


class Task(Thread):

    def __init__(self, name: str, killable: bool = False, **kwargs):
        super(Task, self).__init__(daemon=True, **kwargs)
        # arguments
        self._name: str = name
        self._killable: bool = killable
        # internal state
        self._started: bool = False
        self._finished: bool = False
        # register shutdown handlers
        self._requested_shutdown: bool = False
        dt_shell.shell.on_keyboard_interrupt(self._shutdown)
        dt_shell.shell.on_shutdown(self._shutdown)

    @property
    def name(self) -> str:
        return self._name

    @property
    def killable(self) -> bool:
        return self._killable

    @property
    def started(self) -> bool:
        return self._started

    @property
    def finished(self) -> bool:
        return self._finished

    def run(self) -> None:
        # mark as started
        if DTShellConstants.VERBOSE:
            logger.debug(f"Task '{self._name}' started!")
        self._started = True
        # execute task job
        self.execute()
        # mark as finished
        self._finished = True
        if DTShellConstants.VERBOSE:
            logger.debug(f"Task '{self._name}' finished!")

    def _shutdown(self, event: Event) -> None:
        # prevent multiple shutdown requests
        if self._requested_shutdown:
            return
        self._requested_shutdown = True
        # forward shutdown request to job implementation
        if DTShellConstants.VERBOSE:
            logger.debug(f"Stopping task '{self._name}'...")
        self.shutdown(event)
        # wait for the task to finish if we marked it as not killable
        if not self._killable:
            if DTShellConstants.VERBOSE:
                logger.debug(f"Waiting for task '{self._name}' to finish...")
            self.join()

    @abstractmethod
    def execute(self):
        pass

    @abstractmethod
    def shutdown(self, event: Event):
        pass
