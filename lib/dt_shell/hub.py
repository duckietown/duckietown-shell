import dataclasses
import os
import traceback
from typing import Optional, List

import requests

from dt_shell.utils import pretty_json

import dt_shell

DTHUB_SCHEMA: str = "https"
DTHUB_HOST: str = os.environ.get("DTHUB_HOST", "hub.duckietown.com")
DTHUB_API_VERSION: str = "v1"
DTHUB_API_URL: str = f"{DTHUB_SCHEMA}://{DTHUB_HOST}/api/{DTHUB_API_VERSION}"


@dataclasses.dataclass
class HUBApiResponse:
    messages: List[str]
    result: dict
    code: int


class HUBApiError(Exception):

    def __init__(self, uri: str, response: dict):
        self.uri = uri
        assert not response["success"]
        self.messages: List[str] = response["messages"]
        self.result: dict = response["result"]
        self.code: int = response["code"]

    @property
    def human(self) -> str:
        parts: List[str] = [
            f"An error occurred while communicating with the API endpoint '{self.uri}' on the HUB."
        ]
        if self.code:
            parts.append(f"The error code returned is {self.code}.")
        if self.messages:
            messages: str = "The response contained the following messages:\n\t- " + \
                            "\n\t -".join(self.messages)
            parts.append(messages)
        if self.result:
            result: str = "The response contained the following result:\n" + \
                            pretty_json(self.result, indent_len=4)
            parts.append(result)
        # ---
        return "\n".join(parts)


def hub_api_post(endpoint: str, data: dict, token: Optional[str] = None) -> HUBApiResponse:
    # get token from the profile if not given explicitly
    if token is None:
        token = dt_shell.shell.profile.secrets.dt_token
    # compile url
    url: str = f"{DTHUB_API_URL}/{endpoint.lstrip('/')}"
    response: Optional[dict] = None
    try:
        response = requests.post(
            url,
            json=data,
            headers={"Authorization": f"Token {token}"}
        ).json()
        if not response["success"]:
            raise HUBApiError(endpoint, response)
        return HUBApiResponse(
            messages=response["messages"],
            result=response["result"],
            code=response["code"],
        )
    except HUBApiError as e:
        raise e
    except:
        raise HUBApiError(endpoint, {
            "success": False,
            "messages": [f"Python exception:\n{traceback.format_exc()}"],
            "result": response,
            "code": None,
        })
