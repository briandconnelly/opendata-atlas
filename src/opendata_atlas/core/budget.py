"""Result-size accounting shared by the tools that fit a result to the byte budget.

One guarantee, two measures (rulings 35, 72): a tool's measured result never exceeds
RESULT_LIMIT. `atlas_query_dataset`, reference entry pages and `atlas_find_portals` are measured
by `wire_size`, so a full page with the modern `_meta` stamp and its JSON-RPC frame stays within
RESULT_BYTE_BUDGET. `atlas_describe_dataset` is measured by `payload_size` (ruling 19).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from opendata_atlas.constants import RESULT_BYTE_BUDGET

if TYPE_CHECKING:
    from collections.abc import Callable

    from pydantic import BaseModel

#: Room for the JSON-RPC frame and the protocol fields around the tool result: 759 bytes measured
#: on the modern wire (`_meta` serverInfo stamp, `isError`, frame), rounded up.
ENVELOPE_RESERVE = 1024
#: The byte limit a tool's measured result must not exceed (23,552).
RESULT_LIMIT = RESULT_BYTE_BUDGET - ENVELOPE_RESERVE


def wire_size(result: BaseModel) -> int:
    """Bytes of the tool result as `mcp/result.success` serializes it, text copy included."""
    payload = result.model_dump(mode="json", exclude_none=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    wire = {
        "content": [{"type": "text", "text": text}],
        "structuredContent": payload,
        "isError": False,
    }
    return len(json.dumps(wire, ensure_ascii=False, separators=(",", ":")).encode())


def payload_size(result: BaseModel) -> int:
    """Bytes of `structuredContent` alone, the contract; `wire_size` also counts its text copy.

    Describe is measured this way: the curated pack's fire describe at full detail is about
    31.7 KB on the modern wire, over the budget, and has always shipped; its `structuredContent`
    is 14.1 KB.
    """
    payload = result.model_dump(mode="json", exclude_none=True)
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode())


def fit(
    count: int,
    settle: Callable[[int], None],
    measure: Callable[[], int],
    *,
    limit: int = RESULT_LIMIT,
) -> int:
    """Settle the result on the largest `n <= count` whose `measure()` is within `limit`.

    `settle(n)` puts the first `n` items in the result; size must grow with `n`. Bisects, and
    leaves the result settled at the returned `n`, which is 0 when not even one item fits (the
    caller decides whether an empty result is an error).
    """
    settle(count)
    if measure() <= limit:
        return count
    low, high = 0, count - 1
    while low < high:
        middle = (low + high + 1) // 2
        settle(middle)
        if measure() <= limit:
            low = middle
        else:
            high = middle - 1
    settle(low)
    return low
