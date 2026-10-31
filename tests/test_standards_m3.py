"""Milestone 3 standards review (docs/reviews/2026-10-18-m3-standards.md): regressions."""

from __future__ import annotations

from datetime import date

from opendata_atlas.constants import ISSUES_URL
from opendata_atlas.core import cursor as cursors
from opendata_atlas.core.reference import CAPABILITIES, CAPABILITY_RULES
from opendata_atlas.portals.knowledge import GAP_OFFER, knowledge_notice
from tests.conftest import SEATTLE_CONTEXT, wire

SPD = "33kz-ixgy"  # SPD Call Data: a reviewed Seattle dataset
TODAY = date(2026, 10, 18)


def _section(markdown: str, heading: str) -> str:
    body = markdown.split(f"\n## {heading}\n", 1)[1]
    return body.split("\n## ", 1)[0]


# --- F3 [6.repair-callable]: the index restart is the canonical index call, `{}` ---------


async def test_unreadable_cursor_without_topic_restarts_with_the_index_call(client):
    result = wire(await client.call_tool_mcp("atlas_get_reference", {"cursor": "garbage"}))
    content = result["structuredContent"]
    assert content["code"] == "invalid_cursor"
    assert content["repair"]["next_step"] == "list_items"
    assert content["repair"]["arguments"] == {}, "atlas_get_reference({}) is the index"


async def test_expired_index_cursor_restarts_with_the_index_call(client):
    stale = cursors.encode("reference", {"t": "index", "o": 0, "f": "000000000000"}, portal_id="*")
    result = wire(await client.call_tool_mcp("atlas_get_reference", {"cursor": stale}))
    content = result["structuredContent"]
    assert content["code"] == "cursor_expired", content
    assert content["repair"]["arguments"] == {}


async def test_other_topics_still_restart_on_their_own_first_page(client):
    result = wire(
        await client.call_tool_mcp("atlas_get_reference", {"topic": "soql", "cursor": "garbage"})
    )
    assert result["structuredContent"]["repair"]["arguments"] == {"topic": "soql"}


# --- S-2, A-1, A-2 (Task 6 carry): the knowledge notice's text-column sentence ----------------


def _text_notice(text_filters, **kw):
    notice = knowledge_notice(
        SEATTLE_CONTEXT,
        SPD,
        places=kw.pop("places", {}),
        time_columns=[],
        referenced=kw.pop("referenced", set()),
        today=TODAY,
        text_filters=text_filters,
    )
    assert notice is not None
    return notice.message


def test_text_sentence_reads_in_the_singular_for_one_column():
    message = _text_notice(["area_name"])
    assert (
        "Text column `area_name` filtered or grouped here is not a reviewed place field; "
        "if your answer uses it as an area, say in the answer that its meaning and "
        "completeness are unverified."
    ) in message
    assert "(s)" not in message


def test_text_sentence_reads_in_the_plural_for_several_columns():
    message = _text_notice(["area_name", "crime_type"])
    assert (
        "Text columns `area_name`, `crime_type` filtered or grouped here are not reviewed "
        "place fields; if your answer uses one as an area, say in the answer that its meaning "
        "and completeness are unverified."
    ) in message


def test_text_sentence_skips_a_column_already_named_as_a_place_gap():
    """An unreviewed text place field that the query also filters is named once."""
    message = _text_notice(["area_name"], places={"area_name": None}, referenced={"area_name"})
    assert "No reviewed claim covers place field `area_name`" in message
    assert message.count("`area_name`") == 1, message
    assert "filtered or grouped here" not in message
    assert message.endswith(GAP_OFFER)


def test_text_sentence_keeps_columns_not_named_as_place_gaps():
    message = _text_notice(
        ["area_name", "crime_type"], places={"area_name": None}, referenced={"area_name"}
    )
    assert message.count("`area_name`") == 1, message
    assert "Text column `crime_type` filtered or grouped here" in message


# --- F1 [3.advertised-fields] [2.summary]: hints and unit_of_observation are documented ---


def test_capability_semantics_describe_hints_and_unit_of_observation():
    semantics = _section(CAPABILITIES, "Semantics")
    assert "`hints`" in semantics
    assert "inspect_text_values" in semantics
    assert "`unit_of_observation`" in semantics


def test_hints_rule_is_a_capability_rule():
    rule = "When a query result carries `hints`, follow one before answering that nothing matched."
    assert rule in CAPABILITY_RULES
    assert f"- {rule}" in _section(CAPABILITIES, "Rules").splitlines()


# --- S-1 (R5): the cursor-restart rule defers to a continue_paging repair ----------------


def test_cursor_restart_rule_defers_to_a_continuation_repair():
    rules = _section(CAPABILITIES, "Rules")
    assert rules.index("`continue_paging`") < rules.index("first-page call")


# --- S-4..S-6 (Task 10 carry): the ## Knowledge gaps section -----------------------------


def test_knowledge_gaps_section_states_its_obligations_in_full():
    gaps = _section(CAPABILITIES, "Knowledge gaps")
    lines = gaps.strip().splitlines()
    assert not any(line.startswith(("- Include:", "- Label:")) for line in lines), lines
    assert any("include portal id, dataset id, column, and what was wrong" in s for s in lines)
    assert any("`knowledge-gap` label" in s and "name" in s for s in lines)
    assert ISSUES_URL in gaps, "the section names the tracker, not a pointer to ## Defects"
    assert "never file it unasked" in gaps


# --- A-3: the gap sentence's verb agrees with its subject --------------------------------


def test_gap_sentence_verb_agrees_with_a_plural_effect():
    place_only = _text_notice([], places={"area_name": None}, referenced={"area_name"})
    assert "say in the answer that area breakdowns are unverified." in place_only
    time_only = knowledge_notice(
        SEATTLE_CONTEXT,
        SPD,
        places={},
        time_columns=["some_time"],
        referenced={"some_time"},
        today=TODAY,
    )
    assert time_only is not None
    assert "say in the answer that timestamp timezones are unverified." in time_only.message


# --- Task 16 fix round 1 (review Minors 3-5) --------------------------------------------


def test_hints_semantics_name_the_trigger_and_its_exceptions():
    hints = next(
        line for line in _section(CAPABILITIES, "Semantics").splitlines() if "`hints`" in line
    )
    for phrase in ("clauses-mode", "first page", "`where`", "negated", "alias"):
        assert phrase in hints, phrase
    assert "can carry `hints`" in hints, "a condition, not a promise"


def test_cursor_rule_follows_every_repair_before_restarting():
    """No cursor error leaves the head rule 'Follow repair' and these rules naming two calls.

    #65 split the rule so each obligation is checkable alone; their order is kept."""
    lines = _section(CAPABILITIES, "Rules").splitlines()
    first = next(i for i, line in enumerate(lines) if "`invalid_cursor`" in line)
    assert lines[first].endswith("follow the repair.")
    rules = lines[first : first + 4]
    for step, rule in zip(
        ("`continue_paging`", "`read_paging`"), (rules[1], rules[2]), strict=True
    ):
        assert step in rule, step
    assert "`list_items`" in rules[1]
    assert "first-page call" in rules[2]
    assert rules[3] == "- Never restart a paged call with fewer arguments than its first page."


def test_knowledge_gaps_names_the_tracker_without_a_report_to_fragment():
    gaps = _section(CAPABILITIES, "Knowledge gaps")
    assert "Report to" not in gaps
    assert f"The tracker is {ISSUES_URL}" in gaps


def test_defects_section_states_the_report_as_an_imperative():
    """Final review M-10: no "Report to:" label fragment; INSTRUCTIONS is untouched."""
    from opendata_atlas.core.reference import INSTRUCTIONS

    defects = _section(CAPABILITIES, "Defects")
    assert "Report to" not in defects
    assert f"- Offer the user a defect issue at {ISSUES_URL}" in defects
    assert "never file one unasked" in defects
    assert len(INSTRUCTIONS) == 1_797
