"""
Tolerant argument types for LLM tool schemas.

Models routinely send a JSON-encoded *string* where a list is declared:

    send_player_ids: '["4360761", "4696044"]'   instead of   ["4360761", ...]

Pydantic rejects that before the tool function ever runs ("Input should be a
valid list"), the model gets an error back, and the turn is wasted. In one live
trade run 29% of all tool calls failed this way — enough to stop the agent
converging on a recommendation at all.

The intent in those calls is never ambiguous, so parse it instead of bouncing
it. `StrList` / `DictList` accept the well-formed list, a JSON string holding a
list, a comma-separated string, or a bare scalar, and normalise to a list.

Deliberately NOT tolerated: renamed or missing fields (a model sending
`position=` to a tool that wants `player_id=`). That is a different mistake
about *which* argument to send, and guessing at it would invent data.
"""
from __future__ import annotations

import json
from typing import Annotated, Any, TypeVar

from pydantic import BeforeValidator


def _parse_json_maybe(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def coerce_str_list(value: Any) -> Any:
    """Normalise a model-supplied value into a list of strings."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        parsed = _parse_json_maybe(text)
        if isinstance(parsed, list):
            return [str(v) for v in parsed]
        if isinstance(parsed, (str, int, float)):
            return [str(parsed)]
        # Not JSON: accept a plain comma-separated list.
        if "," in text:
            return [part.strip() for part in text.split(",") if part.strip()]
        return [text]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, (list, tuple)):
        # A single-element list holding a JSON array — seen when a model wraps
        # its stringified list one extra time.
        if len(value) == 1 and isinstance(value[0], str):
            parsed = _parse_json_maybe(value[0].strip())
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        return [str(v) for v in value]
    return value


def coerce_dict_list(value: Any) -> Any:
    """Normalise a model-supplied value into a list of objects."""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        parsed = _parse_json_maybe(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return value
    if isinstance(value, dict):
        # A single object sent where a list of objects was declared.
        return [value]
    return value


_T = TypeVar("_T")

#: `list[str]` that also accepts a JSON string, a CSV string, or a scalar.
StrList = Annotated[list[str], BeforeValidator(coerce_str_list)]


def dict_list(item_type: type[_T]) -> Any:
    """`list[item_type]` that also accepts a JSON string or a single object."""
    return Annotated[list[item_type], BeforeValidator(coerce_dict_list)]
