"""Bounded JSON Schema checks. Never fetch external references."""

import json
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry

from mcp_one.config import Limits


def bounded_json(value: Any, max_bytes: int, max_depth: int = 64) -> int:
    pending = [(value, 0)]
    while pending:
        node, depth = pending.pop()
        if depth > max_depth:
            raise ValueError("JSON exceeds depth limit")
        if isinstance(node, dict):
            pending.extend((v, depth + 1) for v in node.values())
        elif isinstance(node, (list, tuple)):
            pending.extend((v, depth + 1) for v in node)
    size = len(json.dumps(value, allow_nan=False, separators=(",", ":")).encode())
    if size > max_bytes:
        raise ValueError("JSON exceeds byte limit")
    return size


def validate_schema(schema: dict[str, Any], limits: Limits) -> None:
    bounded_json(schema, limits.schema_bytes, limits.schema_depth)
    if schema.get("type") != "object":
        raise ValueError("tool schema root must be object")
    pending: list[Any] = [schema]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"$ref", "$dynamicRef"} and (
                    not isinstance(value, str) or not value.startswith("#")
                ):
                    raise ValueError("external schema references are not supported")
                if key == "$id":
                    raise ValueError("schema base URI changes are not supported")
                if key == "$schema" and value != "https://json-schema.org/draft/2020-12/schema":
                    raise ValueError("JSON Schema 2020-12 required")
                pending.append(value)
        elif isinstance(node, list):
            pending.extend(node)
    Draft202012Validator.check_schema(schema)


def validate_instance(schema: dict[str, Any], value: Any) -> None:
    Draft202012Validator(schema, registry=Registry()).validate(value)
