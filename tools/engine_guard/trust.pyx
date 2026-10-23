import json

cdef extern from "engine_trust.h":
    const char DTM_ENGINE_RELEASE_PUBLIC_KEY[]
    const char DTM_ENGINE_PUBLIC_KEYS[]


def trust():
    return (
        (<bytes>DTM_ENGINE_RELEASE_PUBLIC_KEY).decode("ascii"),
        json.loads((<bytes>DTM_ENGINE_PUBLIC_KEYS).decode("ascii")),
    )
