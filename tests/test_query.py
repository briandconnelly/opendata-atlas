"""Milestone 3: the query engine against recorded data.seattle.gov responses.

Re-record with `RECORD_FIXTURES=1 uv run pytest tests/test_query.py`.
"""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlsplit

import jsonschema
import pytest

from opendata_atlas.constants import RESULT_BYTE_BUDGET
from opendata_atlas.core import cache, query
from tests.conftest import SEATTLE_CONTEXT, framed_size, wire

TOOL = "atlas_query_dataset"
FIRE = "kzjm-xkqj"
CRIME = "tazs-3rd5"
SEPT = "datetime between '2026-09-01T00:00:00' and '2026-09-30T23:59:59'"
THREE_CALLS = "incident_number in ('F260124133', 'F260124199', 'F260124257')"


async def q(client, tools_list, args):
    result = wire(await client.call_tool_mcp(TOOL, args))
    if not result["isError"]:
        schema = next(t["outputSchema"] for t in tools_list["tools"] if t["name"] == TOOL)
        jsonschema.validate(result["structuredContent"], schema)
    return result


def params_of(request_key: str) -> dict[str, str]:
    return dict(json.loads(request_key.split("?", 1)[1]))


def resource_requests(soda) -> list[dict[str, str]]:
    return [params_of(k) for k in getattr(soda, "requests", []) if "/resource/" in k]


@pytest.mark.soda_fixture("query_aggregate_pages")
async def test_aggregate_pages_by_offset_with_group_tiebreak(client, tools_list, soda):
    args = {
        "portal": "seattle",
        "dataset_id": FIRE,
        "select": ["type", "count(*) AS n"],
        "group_by": ["type"],
        "order_by": ["n DESC"],
        "page_size": 5,
    }
    first = (await q(client, tools_list, args))["structuredContent"]
    assert (
        first["returned_rows"] == 5 and first["has_more"] and first["consistency"] == "best_effort"
    )
    assert first["rows"][0] == {"type": "Aid Response", "n": first["rows"][0]["n"]}
    second = (
        await q(
            client,
            tools_list,
            {"portal": "seattle", "dataset_id": FIRE, "cursor": first["next_cursor"]},
        )
    )["structuredContent"]
    assert {r["type"] for r in second["rows"]}.isdisjoint(r["type"] for r in first["rows"])
    sent = resource_requests(soda)
    if sent:
        assert sent[0]["$order"] == "n DESC, type", "group keys break ties"
        assert sent[1]["$offset"] == "5" and sent[1]["$limit"] == "6"


@pytest.mark.soda_fixture("query_keyset_pages")
async def test_unordered_rows_page_by_hidden_id_keyset(client, tools_list, soda):
    args = {
        "portal": "seattle",
        "dataset_id": FIRE,
        "select": ["incident_number", "datetime"],
        "where": SEPT,
        "page_size": 3,
    }
    first = (await q(client, tools_list, args))["structuredContent"]
    assert first["consistency"] == "stable"
    assert [c["name"] for c in first["columns"]] == ["incident_number", "datetime"], (
        ":id stays hidden"
    )
    assert all(":id" not in r for r in first["rows"])
    second = (
        await q(
            client,
            tools_list,
            {"portal": "seattle", "dataset_id": FIRE, "cursor": first["next_cursor"]},
        )
    )["structuredContent"]
    assert {r["incident_number"] for r in second["rows"]}.isdisjoint(
        r["incident_number"] for r in first["rows"]
    )
    sent = resource_requests(soda)
    if sent:
        assert sent[0]["$order"] == ":id" and "$offset" not in sent[1]
        assert ":id > '" in sent[1]["$where"] and sent[1]["$where"].startswith(f"({SEPT})")


@pytest.mark.soda_fixture("query_ordered")
async def test_ordered_rows_add_id_tiebreak(client, tools_list, soda):
    args = {
        "portal": "seattle",
        "dataset_id": FIRE,
        "select": ["incident_number", "datetime"],
        "where": SEPT,
        "order_by": ["datetime DESC"],
        "page_size": 2,
    }
    out = (await q(client, tools_list, args))["structuredContent"]
    assert out["rows"][0]["datetime"] >= out["rows"][1]["datetime"]
    sent = resource_requests(soda)
    if sent:
        assert sent[0]["$order"] == "datetime DESC, :id"


@pytest.mark.soda_fixture("query_wide_rows")
async def test_byte_budget_cuts_whole_rows_and_continues_after_them(client, tools_list, soda):
    args = {"portal": "seattle", "dataset_id": "76t5-zqzr", "page_size": 200}
    result = await q(client, tools_list, args)
    out = result["structuredContent"]
    assert 0 < out["returned_rows"] < 200, "the byte budget, not page_size, ended this page"
    assert out["has_more"] is True
    assert framed_size(result) <= RESULT_BYTE_BUDGET
    assert all(set(r) == {c["name"] for c in out["columns"]} for r in out["rows"]), "nulls restored"
    nxt = (
        await q(
            client,
            tools_list,
            {
                "portal": "seattle",
                "dataset_id": "76t5-zqzr",
                "cursor": out["next_cursor"],
                "page_size": 1,
            },
        )
    )["structuredContent"]
    assert nxt["rows"][0]["permitnum"] not in {r["permitnum"] for r in out["rows"]}


@pytest.mark.soda_fixture("query_wide_rows")
async def test_source_portal_survives_trimming(client, tools_list, soda):
    result = await q(
        client, tools_list, {"portal": "seattle", "dataset_id": "76t5-zqzr", "page_size": 200}
    )
    out = result["structuredContent"]
    assert out["returned_rows"] < 200, "rows were trimmed by the byte budget"
    assert out["source"]["portal"]["id"] == SEATTLE_CONTEXT.id


@pytest.mark.soda_fixture("query_three_rows")
async def test_cap_reached_exactly_is_not_truncated(client, tools_list, soda, monkeypatch):
    monkeypatch.setattr(query, "QUERY_LOGICAL_CAP", 3)
    out = (
        await q(
            client,
            tools_list,
            {
                "portal": "seattle",
                "dataset_id": FIRE,
                "select": ["incident_number"],
                "where": THREE_CALLS,
                "page_size": 5,
            },
        )
    )["structuredContent"]
    assert out["returned_rows"] == 3
    assert out["truncated"] is False and out["has_more"] is False


@pytest.mark.soda_fixture("query_three_rows_capped")
async def test_cap_exceeded_is_truncated_without_cursor(client, tools_list, soda, monkeypatch):
    monkeypatch.setattr(query, "QUERY_LOGICAL_CAP", 2)
    first = (
        await q(
            client,
            tools_list,
            {
                "portal": "seattle",
                "dataset_id": FIRE,
                "select": ["incident_number"],
                "where": THREE_CALLS,
                "page_size": 1,
            },
        )
    )["structuredContent"]
    assert first["has_more"] is True and first["truncated"] is False
    last = (
        await q(
            client,
            tools_list,
            {"portal": "seattle", "dataset_id": FIRE, "cursor": first["next_cursor"]},
        )
    )["structuredContent"]
    assert last["returned_rows"] == 1
    assert last["truncated"] is True and last["has_more"] is False and "next_cursor" not in last
    assert last["truncation_reason"] == "row_cap"


@pytest.mark.soda_fixture("query_raw_soql")
async def test_raw_soql_is_one_page(client, tools_list, soda):
    soql = "SELECT type, count(*) AS n GROUP BY type ORDER BY n DESC LIMIT 50"
    out = (
        await q(
            client,
            tools_list,
            {"portal": "seattle", "dataset_id": FIRE, "mode": "soql", "soql": soql, "page_size": 5},
        )
    )["structuredContent"]
    assert out["returned_rows"] == 5 and out["consistency"] == "single_page"
    assert out["truncated"] is True and out["truncation_reason"] == "raw_soql_not_paged"
    assert "LIMIT 5" in out["truncation_hint"]
    sent = resource_requests(soda)
    if sent:
        assert sent[-1] == {"$query": soql}, "raw SoQL is sent verbatim with nothing added"

    fits = "SELECT type, count(*) AS n GROUP BY type ORDER BY n DESC LIMIT 3"
    small = (
        await q(
            client,
            tools_list,
            {"portal": "seattle", "dataset_id": FIRE, "mode": "soql", "soql": fits, "page_size": 5},
        )
    )["structuredContent"]
    assert small["returned_rows"] == 3 and small["truncated"] is False


@pytest.mark.soda_fixture("query_coverage_warning")
async def test_unreliable_place_field_warns(client, tools_list, soda):
    out = (
        await q(
            client,
            tools_list,
            {
                "portal": "seattle",
                "dataset_id": FIRE,
                "select": ["count(*) AS n"],
                "where": ":@computed_region_cyqu_gs94 = '3'",
            },
        )
    )["structuredContent"]
    warning = out["coverage_warnings"][0]
    assert warning["column"] == ":@computed_region_cyqu_gs94"
    assert warning["reliability"] == "unreliable"


@pytest.mark.soda_fixture("query_coverage_grouped")
async def test_grouping_by_a_partial_place_field_warns_in_both_modes(client, tools_list, soda):
    clauses = {
        "portal": "seattle",
        "dataset_id": CRIME,
        "select": ["neighborhood", "count(*) AS n"],
        "group_by": ["neighborhood"],
        "order_by": ["n DESC"],
        "page_size": 3,
    }
    soql = "SELECT neighborhood, count(*) AS n GROUP BY neighborhood ORDER BY n DESC LIMIT 3"
    raw = {"portal": "seattle", "dataset_id": CRIME, "mode": "soql", "soql": soql, "page_size": 3}
    first = (await q(client, tools_list, clauses))["structuredContent"]
    page_two = {"portal": "seattle", "dataset_id": CRIME, "cursor": first["next_cursor"]}
    for out in (
        first,
        (await q(client, tools_list, page_two))["structuredContent"],
        (await q(client, tools_list, raw))["structuredContent"],
    ):
        assert [(w["column"], w["reliability"]) for w in out.get("coverage_warnings") or []] == [
            ("neighborhood", "partial")
        ]


PARTIAL = [{"column": "neighborhood", "reliability": "partial", "reason": "gaps"}]


@pytest.mark.parametrize(
    ("clauses", "warns"),
    [
        ({"select": ["neighborhood"]}, True),
        ({"select": ["neighborhood AS area"]}, True),
        ({"group_by": ["neighborhood"]}, True),
        ({"order_by": ["neighborhood DESC"]}, True),
        ({"having": "count(neighborhood) > 1"}, True),
        ({"where": "neighborhood = 'CAPITOL HILL'"}, True),
        ({"select": ["count(*) AS neighborhood"]}, False),
        ({"select": ["offense_id AS `offense's id`", "neighborhood", "'a' AS note"]}, True),
        ({"select": ["count(*) AS `neighborhood`"]}, False),
        ({"select": ["`neighborhood`"]}, True),
        ({"select": ["'neighborhood' AS label"]}, False),
        ({"where": "offense = 'neighborhood'"}, False),
        # A later use of a select alias reads the aliased expression, not the column.
        (
            {
                "select": ["precinct AS neighborhood", "count(*) AS n"],
                "group_by": ["precinct"],
                "order_by": ["neighborhood"],
            },
            False,
        ),
        ({"select": ["precinct AS `neighborhood`"], "having": "`neighborhood` > 'A'"}, False),
        ({"select": ["neighborhood AS neighborhood"], "order_by": ["neighborhood"]}, True),
        ({"select": ["precinct AS neighborhood"], "where": "neighborhood = 'X'"}, True),
        ({"select": ["precinct"], "order_by": ["neighborhood"]}, True),
        # A backtick alias is one name, spaces and all.
        (
            {"select": ["precinct AS `neighborhood label`"], "order_by": ["`neighborhood label`"]},
            False,
        ),
    ],
)
def test_coverage_scan_reads_each_clause_but_not_aliases_or_literals(clauses, warns):
    where = [f"({clauses['where']})"] if "where" in clauses else []
    assert (
        bool(query._warnings(query._referenced(*query._written(clauses, where)), PARTIAL)) is warns
    )


@pytest.mark.parametrize(
    ("soql", "warns"),
    [
        ("SELECT neighborhood, count(*) GROUP BY neighborhood", True),
        ("SELECT precinct WHERE neighborhood = 'X'", True),
        (
            "SELECT precinct AS neighborhood, count(*) GROUP BY precinct ORDER BY neighborhood",
            False,
        ),
        ("SELECT precinct AS neighborhood WHERE neighborhood = 'X'", True),
        ("SELECT precinct WHERE offense = 'x order by neighborhood'", False),
        ("select precinct as neighborhood order  by neighborhood desc", False),
        # Keywords inside a backtick identifier are not clause boundaries.
        ("SELECT precinct AS neighborhood, precinct AS `order by`, neighborhood AS area", True),
        ("SELECT count(*) AS `group by neighborhood`", False),
        ("SELECT precinct AS `neighborhood label` ORDER BY `neighborhood label`", False),
    ],
)
def test_raw_soql_scan_resolves_select_aliases(soql, warns):
    assert bool(query._warnings(query._referenced(*query._soql_reads(soql)), PARTIAL)) is warns


@pytest.mark.soda_fixture("query_coverage_implied_select")
async def test_omitted_select_does_not_warn_for_every_place_column(client, tools_list, soda):
    out = (
        await q(
            client,
            tools_list,
            {"portal": "seattle", "dataset_id": CRIME, "where": "offense_id = '0'", "page_size": 1},
        )
    )["structuredContent"]
    assert out.get("coverage_warnings") is None
    sent = resource_requests(soda)
    if sent:
        assert "neighborhood" in sent[-1]["$select"], "the implied select does include the field"


@pytest.mark.soda_fixture("query_near")
async def test_near_on_location_column_with_urls(client, tools_list, soda):
    near = {"column": "location1", "latitude": 47.6062, "longitude": -122.3321, "radius_m": 500}
    out = (
        await q(
            client,
            tools_list,
            {
                "portal": "seattle",
                "dataset_id": "76t5-zqzr",
                "select": ["permitnum"],
                "near": near,
                "page_size": 2,
                "detail": "full",
            },
        )
    )["structuredContent"]
    assert out["returned_rows"] == 2
    assert "within_circle(location1, 47.6062, -122.3321, 500.0)" in out["effective_query"]
    download = parse_qs(urlsplit(out["download_url"]).query)
    assert out["download_url"].startswith("https://data.seattle.gov/resource/76t5-zqzr.csv?")
    assert download["$limit"] == ["1000000000"] and "$offset" not in download
    assert "within_circle" in download["$where"][0]


@pytest.mark.soda_fixture("query_spd_view")
async def test_near_on_redacted_text_column_repairs_to_inspection(client, tools_list, soda):
    near = {"column": "dispatch_latitude", "latitude": 47.6, "longitude": -122.3, "radius_m": 500}
    envelope = (
        await q(client, tools_list, {"portal": "seattle", "dataset_id": "33kz-ixgy", "near": near})
    )["structuredContent"]
    assert envelope["code"] == "column_not_geographic"
    assert envelope["repair"]["arguments"] == {
        "portal": "data.seattle.gov",
        "dataset_id": "33kz-ixgy",
        "detail": "full",
    }
    assert "dispatch_neighborhood" in envelope["repair"]["alternative"]
    assert "not equivalent" in envelope["repair"]["alternative"]


_UPSTREAM_NO_SUCH_COLUMN = (
    400,
    {
        "code": "query.soql.no-such-column",
        "error": True,
        "message": "No such column: nope",
        "data": {"position": {"line": 1, "column": 8, "row": 1}},
    },
)


@pytest.mark.soda_fixture("query_ordered", overrides={"/resource/": _UPSTREAM_NO_SUCH_COLUMN})
async def test_upstream_unknown_column_repairs_to_describe(client, tools_list, soda):
    # A pipe is syntax the pre-check does not model, so upstream decides.
    args = {"portal": "seattle", "dataset_id": FIRE, "select": ["type |> select nope"]}
    envelope = (await q(client, tools_list, args))["structuredContent"]
    assert envelope["code"] == "no_such_column"
    assert envelope["repair"]["tool"] == "atlas_describe_dataset"
    assert "position" not in envelope["details"], "positions of the assembled query are hidden"
    assert (SEATTLE_CONTEXT.id, FIRE) not in cache.views, "a stale schema is dropped"
    assert len(resource_requests(soda)) == 1


@pytest.mark.soda_fixture("query_three_rows", overrides={"/resource/": "timeout"})
async def test_timeout_repairs_toward_narrowing(client, tools_list, soda):
    envelope = (
        await q(
            client,
            tools_list,
            {
                "portal": "seattle",
                "dataset_id": FIRE,
                "select": ["incident_number"],
                "where": THREE_CALLS,
            },
        )
    )["structuredContent"]
    assert envelope["code"] == "query_timeout" and envelope["temporary"] is True
    # A row-returning repair would drop the filters of the query that timed out (#16).
    assert envelope["repair"]["next_step"] == "inspect_for_narrowing"
    assert envelope["repair"]["tool"] == "atlas_describe_dataset"
    assert envelope["repair"]["arguments"] == {"portal": "data.seattle.gov", "dataset_id": FIRE}


@pytest.mark.soda_fixture("query_three_rows", overrides={"/api/views/": "timeout"})
async def test_metadata_timeout_has_no_narrowing_repair(client, tools_list, soda):
    envelope = (
        await q(
            client,
            tools_list,
            {"portal": "seattle", "dataset_id": FIRE, "select": ["incident_number"]},
        )
    )["structuredContent"]
    # Describe would wait on the same metadata; `temporary` alone says retry later.
    assert envelope["code"] == "query_timeout" and envelope["temporary"] is True
    assert "repair" not in envelope
    assert envelope["details"]["reason"] == "The dataset's metadata did not load."


@pytest.mark.soda_fixture("query_three_rows")
async def test_cursor_for_another_dataset_is_rejected(client, tools_list, soda):
    first = (
        await q(
            client,
            tools_list,
            {
                "portal": "seattle",
                "dataset_id": FIRE,
                "select": ["incident_number"],
                "where": THREE_CALLS,
                "page_size": 1,
            },
        )
    )["structuredContent"]
    envelope = (
        await q(
            client,
            tools_list,
            {"portal": "seattle", "dataset_id": "76t5-zqzr", "cursor": first["next_cursor"]},
        )
    )["structuredContent"]
    assert envelope["code"] == "invalid_cursor"
    assert envelope["repair"]["arguments"] == {"topic": "soql", "item_id": "paging"}


def _json_size(clauses: dict) -> int:
    return len(json.dumps(clauses, separators=(",", ":"), ensure_ascii=False).encode())


def _at_cap(key: str, make) -> dict:
    """The largest clauses `make(n)` builds whose compact JSON fits the 4 KiB cap."""
    n = 0
    while _json_size({key: make(n + 1)}) <= 4096:
        n += 1
    return {key: make(n)}


def _where(char: str):
    return lambda n: f"incident_number = '{char * n}'"


_TWO_ROWS = [{":id": "row-1", "incident_number": "a"}, {":id": "row-2", "incident_number": "b"}]
_AT_CAP = {
    "ascii": _at_cap("where", _where("x")),
    "quotes": _at_cap("where", _where('"')),
    "non-ascii": _at_cap("where", _where("é")),
    "many-list-items": _at_cap("order_by", lambda n: ["incident_number"] * n),
}


@pytest.mark.parametrize("clauses", list(_AT_CAP.values()), ids=list(_AT_CAP))
@pytest.mark.soda_fixture("query_three_rows", overrides={"/resource/": (200, _TWO_ROWS)})
async def test_clauses_at_the_cap_page_with_a_cursor_within_6_kib(
    client, tools_list, soda, clauses
):
    result = (
        await q(
            client, tools_list, {"portal": "seattle", "dataset_id": FIRE, "page_size": 1, **clauses}
        )
    )["structuredContent"]
    assert len(result["next_cursor"]) <= 6 * 1024


@pytest.mark.parametrize(
    "clauses",
    [
        pytest.param({"where": "incident_number = '" + '"' * 4070 + "'"}, id="quotes"),
        pytest.param({"order_by": ["incident_number"] * 240}, id="many-list-items"),
    ],
)
async def test_clauses_over_the_cap_as_json_are_rejected(client, tools_list, clauses):
    assert _json_size(clauses) > 4096
    envelope = (await q(client, tools_list, {"portal": "seattle", "dataset_id": FIRE, **clauses}))[
        "structuredContent"
    ]
    assert envelope["code"] == "invalid_argument"


# --------------------------------------------------------------------------
# Column names are checked against the schema before the request (#no_such_column gap)
# --------------------------------------------------------------------------

SCHEMA = [
    {"fieldName": ":id"},
    {"fieldName": "incident_number"},
    {"fieldName": "datetime"},
    {"fieldName": "type"},
]


def _check(clauses: dict) -> None:
    query._check_columns("seattle", FIRE, clauses, SCHEMA)


@pytest.mark.soda_fixture("query_ordered")
@pytest.mark.parametrize(
    ("clauses", "field"),
    [
        ({"select": ["incident_number", "nope"]}, "select"),
        ({"select": ["incident_number"], "where": "nope = 'x'"}, "where"),
        ({"select": ["count(*) AS n"], "group_by": ["nope"]}, "group_by"),
        ({"select": ["count(*) AS n"], "group_by": ["type"], "having": "sum(nope) > 1"}, "having"),
        ({"select": ["incident_number"], "order_by": ["nope DESC"]}, "order_by"),
    ],
)
async def test_unknown_column_fails_before_request(client, tools_list, soda, clauses, field):
    args = {"portal": "seattle", "dataset_id": FIRE, **clauses}
    envelope = (await q(client, tools_list, args))["structuredContent"]
    assert envelope["code"] == "no_such_column"
    assert envelope["details"]["field"] == field
    assert "nope" not in json.dumps(envelope), "the column name is not echoed"
    assert envelope["repair"]["tool"] == "atlas_describe_dataset"
    assert envelope["repair"]["arguments"]["portal"] == SEATTLE_CONTEXT.id
    assert resource_requests(soda) == [], "the portal is never asked"


@pytest.mark.soda_fixture("query_ordered")
async def test_unknown_select_column_fails_before_request(client, tools_list, soda):
    args = {"portal": "seattle", "dataset_id": FIRE, "select": ["call_type"]}
    envelope = (await q(client, tools_list, args))["structuredContent"]
    assert envelope["code"] == "no_such_column"
    assert envelope["repair"]["tool"] == "atlas_describe_dataset"
    assert [k for k in soda.requests if "/resource/" in k] == []


@pytest.mark.parametrize(
    "clauses",
    [
        {"select": ["count(*) AS n", "type"], "group_by": ["type"], "order_by": ["n DESC"]},
        {"select": ["date_trunc_ym(datetime) AS month", "count(*)"], "group_by": ["month"]},
        {"select": ["type AS `kind of call`"], "order_by": ["`kind of call`"]},
        {"select": ["count(*) AS n", "type"], "group_by": ["type"], "having": "n > 3"},
        {"select": ["distinct type"], "where": "type IS NOT NULL AND type LIKE 'A%'"},
        {
            "select": ["incident_number"],
            "where": "type in ('a', 'nope') OR datetime > '2026-01-01'",
        },
        {"select": [":id", ":created_at", ":@computed_region_abcd_1234"]},
        {"select": ["incident_number"], "where": "datetime::text = 'x'", "order_by": ["TYPE"]},
        {"select": ["type"], "order_by": ["type DESC NULLS LAST"], "where": "1e5 > 2.5"},
        {"select": ["case(type = 'a', 1, true, 2) AS c"], "near": None},
        {"select": ["count(*) AS n", "type"], "where": "n > 1"},
        {"select": ["incident_number"], "where": 'type = "Aid Response"'},
        {"select": ["incident_number"], "where": "type :: text = 'x'"},
        {"select": ["incident_number"], "where": "datetime::text = 'x' and type ::text = 'y'"},
        {"select": ["row_number() over (partition by type order by datetime) AS r"]},
        {"select": ["rank() OVER(partition by nope) AS r"]},
        {"select": ["type |> select count(*)"]},
        {"select": ["type |> select type AS t"], "where": "t = 'x'"},
        {"select": ["type"], "where": "type |> select type AS t", "order_by": ["t"]},
        {"select": ["incident_number"], "where": "datetime = \"O'Brien St\" and type = 'x'"},
        {"select": ["incident_number"], "where": "type = 'say \"hi\"' and datetime = 'x'"},
        {"select": ["incident_number"], "where": "type = 'it''s' and datetime = \"a\"\"b\""},
        {"select": ["incident_number"], "where": 'nope = "abc'},
        {"select": ["incident_number"], "where": "type = 'abc", "order_by": ["nope"]},
        {"select": ["nope"], "where": "row_number() over (order by type) > 1"},
        {"select": ["incident_number"], "where": "nope |> select 1"},
        {},
    ],
)
def test_alias_and_function_names_are_not_columns(clauses):
    _check(clauses)


@pytest.mark.parametrize(
    "clauses",
    [
        pytest.param({"select": ["name.name"]}, id="dotted-subfield"),
        pytest.param({"select": ["type.name", "incident_number"]}, id="dotted-known-base"),
        pytest.param({"select": ["type"], "where": "location.latitude > 47.5"}, id="dotted-where"),
        pytest.param({"select": ["type"], "where": "type ilike 'a%'"}, id="ilike"),
        pytest.param({"select": ["type"], "where": "type ILIKE 'a%'"}, id="ilike-upper"),
        *(
            pytest.param(
                {
                    "select": ["type", f"{fn}({arg})"],
                    "group_by": ["type"],
                    "order_by": [f"{fn} DESC"],
                },
                id=f"implicit-{fn}",
            )
            for fn, arg in [
                ("count", "*"),
                ("sum", "incident_number"),
                ("avg", "incident_number"),
                ("min", "datetime"),
                ("max", "datetime"),
            ]
        ),
    ],
)
def test_names_the_check_cannot_be_sure_of_pass(clauses):
    """Ruling 16: dotted subfields, `ilike` and implicit aggregate aliases fail open."""
    _check(clauses)


@pytest.mark.parametrize(
    "clauses",
    [
        pytest.param({"select": ["type"], "where": "nope ilike 'a%'"}, id="ilike-unknown"),
        pytest.param({"select": ["type"], "order_by": ["count DESC"]}, id="count-no-aggregate"),
        pytest.param(
            {"select": ["type", "sum(incident_number)"], "order_by": ["count"]},
            id="count-other-aggregate",
        ),
    ],
)
def test_fail_open_rules_still_catch_unknown_names(clauses):
    with pytest.raises(query.AtlasError):
        _check(clauses)


@pytest.mark.soda_fixture("query_ordered", overrides={"/resource/": (200, [])})
async def test_alias_in_where_reaches_the_portal(client, tools_list, soda):
    # Seattle and LA accept a select alias in $where (review), so the check cannot reject it.
    args = {
        "portal": "seattle",
        "dataset_id": FIRE,
        "select": ["count(*) AS n", "type"],
        "group_by": ["type"],
        "where": "n > 1",
    }
    out = await q(client, tools_list, args)
    assert not out["isError"]
    assert len(resource_requests(soda)) == 1


@pytest.mark.parametrize(
    "where",
    ['nope = "x"', "nope = 'x'", "datetime = \"O'Brien St\" and nope = 'x'", "nope = 'it''s'"],
)
def test_an_unknown_name_beside_quoted_strings_is_still_caught(where):
    with pytest.raises(query.AtlasError):
        _check({"select": ["incident_number"], "where": where})


def test_an_unknown_name_after_a_function_call_is_still_caught():
    with pytest.raises(query.AtlasError):
        _check({"select": ["upper(type)", "nope"]})


# --- Milestone 3 Task 7: a text equality filter that matched nothing ----------

HINTED = "aaaa-bbbb"
_HINT_COLUMNS = [
    {"fieldName": "area_name", "dataTypeName": "text"},
    {"fieldName": "crime_type", "dataTypeName": "text"},
    {"fieldName": "status_desc", "dataTypeName": "text"},
    {"fieldName": "n_count", "dataTypeName": "number"},
    {"fieldName": "date_rptd", "dataTypeName": "floating_timestamp"},
]


def install_hint_view(pages: list[list[dict]], fields: list[str]) -> list[dict[str, str]]:
    """A fake portal serving `_HINT_COLUMNS`; each resource request gets the next page of rows.

    Returns the resource requests' parameters, appended as they arrive."""
    import httpx

    from opendata_atlas.core.http import SodaClient, set_client

    view = {"id": HINTED, "assetType": "dataset", "viewType": "tabular", "columns": _HINT_COLUMNS}
    sent: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "/api/views/" in request.url.path:
            return httpx.Response(200, json=view)
        sent.append(dict(request.url.params))
        rows = pages[min(len(sent), len(pages)) - 1]
        headers = {
            "X-SODA2-Fields": json.dumps(fields),
            "X-SODA2-Types": json.dumps(["text"] * len(fields)),
        }
        return httpx.Response(200, headers=headers, content=json.dumps(rows).encode())

    cache.clear()
    set_client(SodaClient(transport=httpx.MockTransport(handler)))
    return sent


def _hint_args(**clauses) -> dict:
    return {"portal": "seattle", "dataset_id": HINTED, **clauses}


async def test_zero_rows_on_text_equality_gets_hint(client, tools_list, input_schemas):
    install_hint_view([[]], ["area_name"])
    out = (
        await q(
            client, tools_list, _hint_args(select=["area_name"], where="area_name = 'Hollywood'")
        )
    )["structuredContent"]
    assert out["returned_rows"] == 0
    [hint] = out["hints"]
    assert hint == {
        "next_step": "inspect_text_values",
        "tool": "atlas_query_dataset",
        "arguments": {
            "portal": SEATTLE_CONTEXT.id,
            "dataset_id": HINTED,
            "select": ["area_name", "count(*) AS n"],
            "group_by": ["area_name"],
            "order_by": ["n DESC"],
            "where": "upper(area_name) like '%HOLLYWOOD%'",
        },
        "alternative": "No rows matched `area_name` = 'Hollywood'; its values may be padded "
        "or differ in case, so filter on a value this grouping returns.",
    }
    jsonschema.validate(hint["arguments"], input_schemas[TOOL])


async def test_zero_count_aggregate_gets_hint(client, tools_list):
    install_hint_view([[{"n": "0"}]], ["n"])
    out = (
        await q(
            client,
            tools_list,
            _hint_args(select=["count(*) AS n"], where="area_name = 'Hollywood'"),
        )
    )["structuredContent"]
    assert out["rows"] == [{"n": "0"}]
    assert [h["arguments"]["group_by"][0] for h in out["hints"]] == ["area_name"]


async def test_hint_repair_keeps_other_filters(client, tools_list):
    install_hint_view([[]], ["area_name"])
    where = "date_rptd >= '2026-09-01' AND area_name = 'Hollywood'"
    out = (
        await q(
            client,
            tools_list,
            _hint_args(select=["area_name"], where=where, search_text="theft"),
        )
    )["structuredContent"]
    arguments = out["hints"][0]["arguments"]
    assert arguments["where"] == "date_rptd >= '2026-09-01' AND upper(area_name) like '%HOLLYWOOD%'"
    assert arguments["search_text"] == "theft"
    assert "near" not in arguments


async def test_literal_with_quote_and_wildcards(client, tools_list, input_schemas):
    install_hint_view([[]], ["area_name"])
    out = (
        await q(
            client, tools_list, _hint_args(select=["area_name"], where="area_name = 'O''Brien_%'")
        )
    )["structuredContent"]
    [hint] = out["hints"]
    assert "'%O''BRIEN_%%'" in hint["arguments"]["where"]
    assert hint["alternative"].startswith("No rows matched `area_name` = 'O''Brien_%';")
    jsonschema.validate(hint["arguments"], input_schemas[TOOL])
    query._check_columns(SEATTLE_CONTEXT.id, HINTED, hint["arguments"], _HINT_COLUMNS)


async def test_number_equality_gets_no_hint(client, tools_list):
    install_hint_view([[]], ["n_count"])
    out = (await q(client, tools_list, _hint_args(select=["n_count"], where="n_count = '5'")))[
        "structuredContent"
    ]
    assert out["returned_rows"] == 0 and "hints" not in out


async def test_nonempty_page_gets_no_hint(client, tools_list):
    install_hint_view([[{"n": "3"}]], ["n"])
    out = (
        await q(client, tools_list, _hint_args(select=["count(*) AS n"], where="area_name = 'X'"))
    )["structuredContent"]
    assert out["returned_rows"] == 1 and "hints" not in out


async def test_grouped_zero_row_gets_no_hint(client, tools_list):
    install_hint_view([[{"area_name": None, "n": "0"}]], ["area_name", "n"])
    out = (
        await q(
            client,
            tools_list,
            _hint_args(
                select=["area_name", "count(*) AS n"],
                group_by=["area_name"],
                where="crime_type = 'X'",
            ),
        )
    )["structuredContent"]
    assert out["returned_rows"] == 1 and "hints" not in out


async def test_continuation_page_gets_no_hint(client, tools_list):
    first_page = [{"area_name": "A", ":id": "row-1"}, {"area_name": "A", ":id": "row-2"}]
    sent = install_hint_view([first_page, []], ["area_name", ":id"])
    args = _hint_args(select=["area_name"], where="area_name = 'A'", page_size=1)
    first = (await q(client, tools_list, args))["structuredContent"]
    assert "hints" not in first and first["next_cursor"]
    nxt = (await q(client, tools_list, _hint_args(cursor=first["next_cursor"])))[
        "structuredContent"
    ]
    assert nxt["returned_rows"] == 0 and "hints" not in nxt
    assert len(sent) == 2, "the empty page came from upstream"


async def test_one_hint_per_column_and_each_repair_replaces_its_own_match(client, tools_list):
    install_hint_view([[]], ["area_name"])
    where = "(area_name = 'a' OR area_name = 'b') AND crime_type = 'c' AND n_count = '1'"
    out = (await q(client, tools_list, _hint_args(select=["area_name"], where=where)))[
        "structuredContent"
    ]
    assert [h["arguments"]["group_by"][0] for h in out["hints"]] == ["area_name", "crime_type"]
    area, crime = (h["arguments"]["where"] for h in out["hints"])
    assert (
        area
        == "(upper(area_name) like '%A%' OR area_name = 'b') AND crime_type = 'c' AND n_count = '1'"
    )
    assert (
        crime
        == "(area_name = 'a' OR area_name = 'b') AND upper(crime_type) like '%C%' AND n_count = '1'"
    )


def test_equality_text_inside_a_string_literal_is_not_a_filter():
    hints = query._hints(
        "seattle", HINTED, {"where": "crime_type like '%area_name = ''x''%'"}, _HINT_COLUMNS
    )
    assert hints == []


# --- Task 7 fix round 1: ruling 48 and the review minors -----------------------


@pytest.mark.parametrize(
    ("select", "row"),
    [
        (["sum(n_count) AS s"], {"s": "0"}),  # a legitimately zero sum
        (["count(crime_type) AS c"], {"c": "0"}),  # count(col) over rows whose col is null
        (["n_count", "crime_type"], {"n_count": "0", "crime_type": None}),  # a matched row
    ],
)
async def test_one_zero_row_without_count_star_gets_no_hint(client, tools_list, select, row):
    install_hint_view([[row]], list(row))
    out = (await q(client, tools_list, _hint_args(select=select, where="area_name = 'X'")))[
        "structuredContent"
    ]
    assert out["returned_rows"] == 1 and "hints" not in out


async def test_unaliased_count_star_zero_gets_hint(client, tools_list):
    install_hint_view([[{"count": "0"}]], ["count"])
    out = (await q(client, tools_list, _hint_args(select=["count(*)"], where="area_name = 'X'")))[
        "structuredContent"
    ]
    assert [h["arguments"]["group_by"][0] for h in out["hints"]] == ["area_name"]


async def test_zero_row_page_with_more_rows_gets_no_hint(client, tools_list):
    zeros = [{"n_count": "0", ":id": "row-1"}, {"n_count": "0", ":id": "row-2"}]
    install_hint_view([zeros], ["n_count", ":id"])
    args = _hint_args(select=["n_count"], where="area_name = 'X'", page_size=1)
    out = (await q(client, tools_list, args))["structuredContent"]
    assert out["has_more"] and "hints" not in out


async def test_hint_repair_never_exceeds_the_clause_cap(client, tools_list, input_schemas):
    install_hint_view([[]], ["area_name"])
    pad = "x" * (4096 - 120)
    where = f"date_rptd >= '{pad}' AND area_name = 'Hollywood'"
    out = (await q(client, tools_list, _hint_args(select=["area_name"], where=where)))[
        "structuredContent"
    ]
    assert out["returned_rows"] == 0, "the call itself is within the cap"
    assert "hints" not in out, "a repair over the cap would be invalid_argument"


async def test_hint_alternative_is_bounded_and_hints_fit_the_budget(client, tools_list):
    install_hint_view([[]], ["area_name"])
    long = "y" * 1200
    where = f"area_name = '{long}' AND crime_type = '{long}' AND status_desc = '{long}'"
    result = await q(client, tools_list, _hint_args(select=["area_name"], where=where))
    out = result["structuredContent"]
    assert 0 < len(out["hints"]) < 3, "three repairs fit the clause cap; the budget drops one"
    for hint in out["hints"]:
        assert len(hint["alternative"]) < 300
        jsonschema.validate(hint["arguments"], input_schemas_of(tools_list))
    assert framed_size(result) <= RESULT_BYTE_BUDGET


def input_schemas_of(tools_list) -> dict:
    return next(t["inputSchema"] for t in tools_list["tools"] if t["name"] == TOOL)


async def test_where_reading_a_select_alias_gets_no_hint(client, tools_list):
    install_hint_view([[]], ["m"])
    args = _hint_args(
        select=["date_trunc_ym(date_rptd) AS m"], where="m = '2026-09' AND area_name = 'X'"
    )
    out = (await q(client, tools_list, args))["structuredContent"]
    assert out["returned_rows"] == 0 and "hints" not in out


@pytest.mark.parametrize(
    "where",
    ["NOT area_name = 'X'", "not (area_name = 'X')", "NOT (crime_type = 'a' AND area_name = 'X')"],
)
def test_negated_equality_gets_no_hint(where):
    assert query._hints(SEATTLE_CONTEXT.id, HINTED, {"where": where}, _HINT_COLUMNS) == []


@pytest.mark.parametrize(
    "where",
    [
        "crime_type IS NOT NULL AND area_name = 'X'",
        "crime_type NOT IN ('a') AND area_name = 'X'",
        "crime_type NOT LIKE '%a%' AND area_name = 'X'",
    ],
)
def test_not_as_part_of_an_operator_still_hints(where):
    hints = query._hints(SEATTLE_CONTEXT.id, HINTED, {"where": where}, _HINT_COLUMNS)
    assert [h.arguments["group_by"][0] for h in hints] == ["area_name"]
