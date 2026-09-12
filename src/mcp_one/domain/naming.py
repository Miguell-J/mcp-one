import re


def qualified_name(namespace: str, downstream_name: str) -> str:
    name = (
        downstream_name
        if downstream_name.startswith(namespace + ".")
        else (namespace + "." + downstream_name)
    )
    if not downstream_name or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name):
        raise ValueError("invalid or oversized aggregate tool name")
    return name
