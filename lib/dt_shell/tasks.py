import json
import traceback
from abc import abstractmethod
from threading import Thread
from typing import Optional

import requests
from requests import JSONDecodeError, Response

from dt_shell.utils import DebugInfo

import dockertown
from dt_shell.database import DTShellDatabase

from dt_shell_cli import logger
from .constants import DTShellConstants, DTHUB_URL, DB_BILLBOARDS
from .hub import HUBApiError, hub_api_post
from .shell import Event, DTShell
from .statistics import ShellProfileEventsDatabase


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
        try:
            self.execute()
        except KeyboardInterrupt:
            logger.debug(f"Task '{self._name}' interrupted by SIGINT!")
        finally:
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
        url: str = f"{DTHUB_URL}/api/v1/billboard/list/"
        raw: Optional[Response] = None
        # reach out to the HUB and grub the new billboards
        try:
            logger.debug(f"GET {url}")
            raw = requests.get(url)
            response: dict = raw.json()
            self._shell.profile.events.new("shell/billboards/update")
        except JSONDecodeError:
            logger.warning("An error occurred while decoding the received billboards. Use --verbose for further info")
            logger.debug(traceback.format_exc())
            logger.debug("HUB response:\n" + str(raw))
            # mark as updated so we don't retry right away
            self._shell.mark_updated("billboards")
            return
        except Exception:
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
        for bboard in response.get("result", {}).get("results", []):
            self._db.set(bboard["name"], bboard)
        self._shell.mark_updated("billboards")
        logger.debug("Billboards updated!")

    def shutdown(self, event: Event):
        pass


class CollectDockerVersionTask(Task):

    def __init__(self, shell, **kwargs):
        super(CollectDockerVersionTask, self).__init__(shell, name="docker-version-probe", killable=True,
                                                       **kwargs)
        self._db: DTShellDatabase = DTShellDatabase.open(DB_BILLBOARDS)

    def execute(self):
        try:
            # create docker client
            docker = dockertown.DockerClient()
            # get versions
            versions: dict = docker.version()
            DebugInfo.name2versions["docker/client"] = versions["Client"]["Version"]
            DebugInfo.name2versions["docker/server"] = versions["Server"]["Version"]
            DebugInfo.name2versions["docker/client/api"] = versions["Client"]["ApiVersion"]
            DebugInfo.name2versions["docker/server/api"] = versions["Server"]["ApiVersion"]
        except:
            DebugInfo.name2versions["docker/client"] = "(error)"
            DebugInfo.name2versions["docker/server"] = "(error)"
            DebugInfo.name2versions["docker/client/api"] = "(error)"
            DebugInfo.name2versions["docker/server/api"] = "(error)"

    def shutdown(self, event: Event):
        pass


class UploadStatisticsTask(Task):

    def __init__(self, shell, **kwargs):
        super(UploadStatisticsTask, self).__init__(shell, name="stats-uploader", killable=True, **kwargs)
        self._db: ShellProfileEventsDatabase = shell.profile.events
        self._token: Optional[str] = shell.profile.secrets.dt_token

    def execute(self):
        if self._token is None:
            return
        # push events
        for evt in self._db.events():
            try:
                data: dict = {
                    "key": evt.name,
                    "format": evt.format,
                    "payload": evt.payload,
                    "stamp": evt.time_millis
                }
                if evt.labels:
                    data["labels"] = evt.labels
                hub_api_post("statistics/user/event", data)
                evt.delete()
                if DTShellConstants.VERBOSE:
                    logger.debug(f"Event '{evt.__key__}' pushed to the HUB")
            except HUBApiError as e:
                if e.code == 409:
                    # duplicated stats points
                    evt.delete()
                    continue
                if DTShellConstants.VERBOSE:
                    logger.debug(e.human)
            except:
                if DTShellConstants.VERBOSE:
                    logger.debug(traceback.format_exc())
        # mark as done
        self._shell.mark_done("upload_events")

    def shutdown(self, event: Event):
        pass

