import json

cdef extern from "viewer_trust.h":
    const char DTV_RELEASE_PUBLIC_KEY[]
    const char DTV_AUTH_PUBLIC_KEYS[]


def trust():
    return (
        (<bytes>DTV_RELEASE_PUBLIC_KEY).decode("ascii"),
        json.loads((<bytes>DTV_AUTH_PUBLIC_KEYS).decode("ascii")),
    )
