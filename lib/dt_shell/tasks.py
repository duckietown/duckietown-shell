import json
import traceback
from abc import abstractmethod
from threading import Thread
from typing import Optional

import requests
from dt_authentication import DuckietownToken

from dt_shell.profile import ShellProfile

from dt_shell.database import DTShellDatabase

from dt_shell_cli import logger
from .constants import DTShellConstants, DTHUB_URL, DB_BILLBOARDS
from .shell import Event, DTShell


class Task(Thread):

    def __init__(self, shell: DTShell, name: str, killable: bool = False, **kwargs):
        super(Task, self).__init__(daemon=True, **kwargs)
        # arguments
        self._shell: DTShell = shell
        self._name: str = name
        self._killable: bool = killable
        # internal state
        self._has_started: bool = False
        self._has_finished: bool = False
        # register shutdown handlers
        self._requested_shutdown: bool = False
        self._shell.on_keyboard_interrupt(self._shutdown)
        self._shell.on_shutdown(self._shutdown)

    @property
    def name(self) -> str:
        return self._name

    @property
    def killable(self) -> bool:
        return self._killable

    @property
    def started(self) -> bool:
        return self._has_started

    @property
    def finished(self) -> bool:
        return self._has_finished

    def run(self) -> None:
        # mark as started
        if DTShellConstants.VERBOSE:
            logger.debug(f"Task '{self._name}' started!")
        self._has_started = True
        # execute task job
        self.execute()
        # mark as finished
        self._has_finished = True
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


class UpdateBillboardsTask(Task):

    def __init__(self, shell, **kwargs):
        super(UpdateBillboardsTask, self).__init__(shell, name="billboards-updater", **kwargs)
        self._db: DTShellDatabase = DTShellDatabase.open(DB_BILLBOARDS)

    def execute(self):
        url: str = f"{DTHUB_URL}/api/v1/shell/billboards"
        # reach out to the HUB and grub the new billboards
        try:
            response: dict = requests.get(url).json()
        except KeyboardInterrupt:
            return
        except:
            logger.warning("An error occurred while updating the billboards")
            logger.debug(traceback.format_exc())
            # mark as updated so we don't retry right away
            self._shell.mark_updated("billboards")
            return
        # check response
        if response.get("success", False) is not True:
            logger.warning("An error occurred while updating the billboards")
            logger.debug("HUB response:\n" + json.dumps(response, indent=4, sort_keys=True))
            # mark as updated so we don't retry right away
            self._shell.mark_updated("billboards")
            return
        # update local database
        self._db.clear()
        self._db.update(response.get("result", {}))
        self._shell.mark_updated("billboards")
        logger.debug("Billboards updated!")

    def shutdown(self, event: Event):
        pass


class ShellTokenTask(Task):

    def __init__(self, shell, **kwargs):
        super(ShellTokenTask, self).__init__(shell, name="shell-token-updater", **kwargs)

    def execute(self):
        profile: ShellProfile = self._shell.profile
        if profile is None:
            return
        # we have a profile, check if we have a token
        db: DTShellDatabase = profile.database("shell-token")
        token_str: str = db.get("token", None)
        # parse token
        try:
            token: Optional[DuckietownToken] = DuckietownToken.from_string(token_str) if token_str else None
        except:
            logger.debug(traceback.format_exc())
            # drop token, we will create a new one later
            if token_str is not None:
                db.delete("token")
            return
        # no token or out-of-scope token
        if token_str is None or token is None or not token.grants("run", "shell"):
            # no valid tokens yet, let's try and fetch a new one
            auth_token: str = profile.secrets.dt_token
            if auth_token is None:
                return
            create_url: str = f"{DTHUB_URL}/v1/token/create/run:shell"
            try:
                response: dict = requests.get(
                    create_url,
                    headers={"Authorization": f"Token {auth_token}"}
                ).json()
            except:
                # we have to give up
                logger.debug(traceback.format_exc())
                # mark as updated so we don't retry right away
                profile.mark_updated("shell-token")
                return
        else:
            # we have a token
            try:
                token: DuckietownToken = DuckietownToken.from_string(token_str)
            except:
                logger.debug(traceback.format_exc())
                # drop token, we will create a new one later
                db.delete("token")
                return
            # token is parsed
            if not token.expired:
                # all good
                profile.mark_updated("shell-token")
                return
            # renew token
            renew_url: str = f"{DTHUB_URL}/v1/token/renew"
            try:
                response: dict = requests.get(
                    renew_url,
                    headers={"Authorization": f"Token {token_str}"}
                ).json()
            except:
                # we have to give up
                logger.debug(traceback.format_exc())
                # mark as updated so we don't retry right away
                profile.mark_updated("shell-token")
                return

        # check response
        if response.get("success", False) is not True:
            logger.debug("AUTH response:\n" + json.dumps(response, indent=4, sort_keys=True))
            # mark as updated so we don't retry right away
            self._shell.mark_updated("shell-token")
            return
        token_str: str = response.get("result", {}).get("token", None)
        if token_str is None:
            logger.debug("AUTH returned no tokens")
            # mark as updated so we don't retry right away
            self._shell.mark_updated("shell-token")
            return
        # we received a token
        try:
            DuckietownToken.from_string(token_str)
        except:
            # this should not have happened
            logger.debug(traceback.format_exc())
            # mark as updated so we don't retry right away
            self._shell.mark_updated("shell-token")
            return
        # set token
        db.set("token", token_str)
        db.set("messages", response.get("messages", []))

    def shutdown(self, event: Event):
        pass
