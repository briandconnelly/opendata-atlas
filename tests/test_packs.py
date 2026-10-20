import shutil
from pathlib import Path
from typing import get_args

import pytest

from opendata_atlas.portals.loader import SEATTLE, PackError, load_portal
from opendata_atlas.portals.model import Claim, Pack
from tests.conftest import PORTALS_DIR

EXAMPLES = Path(__file__).resolve().parent.parent / "docs" / "pack-examples"


def test_malformed_pack_fails_at_load_naming_file(tmp_path):
    shutil.copytree(SEATTLE, tmp_path / "p")
    (tmp_path / "p" / "portal.toml").write_text('id = "data.seattle.gov"\ntimezone = 7\n')
    with pytest.raises(PackError, match=r"portal\.toml.*timezone"):
        load_portal(tmp_path / "p")


def test_every_shipped_pack_loads():
    loaded = 0
    for d in PORTALS_DIR.iterdir():
        if (d / "portal.toml").exists():
            load_portal(d)
            loaded += 1
    assert loaded >= 1


_CLAIM_TOML = """
[[claim]]
id = "a-place"
kind = "place_field"
scope = {dataset = "aaaa-bbbb", column = "hood"}
interpretation = {kind = "neighborhood", reliability = "partial", reason = "r"}
placeholders = ["-"]
reviewed_by = "claude"
reviewed_at = 2026-10-16

[[claim.evidence]]
kind = "soql_probe"
query = "SELECT 1"
observed_at = 2026-10-16
observation = "o"

[[claim.assertion]]
checker = "value_present"
params = {column = "v", value = "-"}
"""


def _pack(tmp_path, name, text):
    d = tmp_path / "p"
    shutil.copytree(SEATTLE, d)
    target = d / name
    target.parent.mkdir(exist_ok=True)
    target.write_text(text)
    return d


def test_design_format_claim_loads_and_is_found(tmp_path):
    ctx = load_portal(_pack(tmp_path, "facts/aaaa-bbbb.toml", _CLAIM_TOML))
    assert ctx.pack.place_fields("aaaa-bbbb")["hood"].id == "a-place"
    assert ctx.pack.place_fields("zzzz-zzzz") == {}
    assert ctx.pack.placeholders("aaaa-bbbb", "hood") == frozenset({"-"})  # engine gap 2


def test_claims_key_rejected(tmp_path):
    d = _pack(tmp_path, "regions.toml", "[[claims]]\nid = 'x'\n")
    with pytest.raises(PackError, match=r"regions\.toml.*claims"):
        load_portal(d)


def test_duplicate_claim_ids_rejected(tmp_path):
    d = _pack(tmp_path, "facts/a.toml", _CLAIM_TOML)
    (d / "facts" / "b.toml").write_text(_CLAIM_TOML)
    with pytest.raises(PackError, match="duplicate claim ids"):
        load_portal(d)


def test_guides_import_error_wrapped(tmp_path):
    d = _pack(tmp_path, "guides.py", "raise RuntimeError('boom')\n")
    with pytest.raises(PackError, match=r"guides\.py: guides: boom"):
        load_portal(d)


def test_pack_lookups():
    ev = [{"kind": "document", "url": "u", "quote": "q", "observed_at": "2026-10-16"}]

    def mk(cid, kind, **scope):
        return Claim.model_validate(
            {
                "id": cid,
                "kind": kind,
                "scope": scope,
                "evidence": ev,
                "placeholders": ["-", "UNKNOWN"] if kind == "placeholder_share" else None,
                # Only a reviewed declaration counts (Task 9 review).
                **(
                    {"reviewed_by": "test", "reviewed_at": "2026-10-16"}
                    if kind == "placeholder_share"
                    else {}
                ),
            }
        )

    pack = Pack(
        claims=[
            mk("pf", "place_field", dataset="d1", column="c1"),
            mk("rl", "region_layer", layer="L"),
            mk("tz", "column_timezone", dataset="d1", column="t"),
            mk("ph", "placeholder_share", dataset="d1", column="c1"),
        ]
    )
    assert set(pack.place_fields("d1")) == {"c1"}
    assert (rl := pack.region_layer("L")) is not None and rl.id == "rl"
    assert pack.region_layer("M") is None
    assert (tz := pack.column_timezone("d1", "t")) is not None and tz.id == "tz"
    assert pack.column_timezone("d1", "x") is None
    assert pack.placeholders("d1", "c1") == frozenset({"-", "UNKNOWN"})
    assert pack.placeholders("d1", "nope") == frozenset()


# --- Task 7: Seattle knowledge as a pack -----------------------------------------


def test_seattle_pack_reproduces_legacy_facts():
    pack = load_portal(SEATTLE).pack
    neighborhood = pack.place_fields("tazs-3rd5")["neighborhood"].interpretation
    assert neighborhood is not None and neighborhood.reliability == "partial"
    council = pack.region_layer("cyqu-gs94")
    assert council is not None and council.interpretation is not None
    assert council.interpretation.reliability == "unreliable"
    queued = pack.column_timezone("33kz-ixgy", "cad_event_original_time_queued")
    assert queued is not None and queued.interpretation is not None
    assert queued.interpretation.timezone == "America/Los_Angeles"
    assert pack.placeholders("33kz-ixgy", "dispatch_neighborhood") == frozenset(
        {"-", "UNKNOWN", "NULL", "OOJ", "FK ERROR", "X", "0", ""}
    )
    assert pack.placeholders("33kz-ixgy", "not_a_place_field") == frozenset()


def test_seattle_pack_ships_one_facts_file_per_dataset():
    names = {p.stem for p in (SEATTLE / "facts").glob("*.toml")}
    assert names == {"33kz-ixgy", "tazs-3rd5", "ppi5-g2bj", "76t5-zqzr", "kzjm-xkqj", "65db-xm6k"}
    assert (SEATTLE / "regions.toml").exists()


def test_seattle_guides_come_from_the_pack():
    ctx = load_portal(SEATTLE)
    assert [g.guide_id for g in ctx.guides][:1] == ["fire-911"]
    assert ctx.guides_by_dataset["kzjm-xkqj"].guide_id == "fire-911"
    assert ctx.guides_by_id["fire-911"].dataset_id == "kzjm-xkqj"


async def test_claim_for_missing_column_is_ignored():  # Review Focus 2
    from opendata_atlas.core import describe
    from opendata_atlas.core.http import SodaClient
    from tests.conftest import with_extra_claim
    from tests.http_fixtures import Replay

    client = SodaClient(transport=Replay("describe_fire_full"))
    ctx = with_extra_claim(
        load_portal(SEATTLE), dataset="kzjm-xkqj", column="gone_column", reliability="ok"
    )
    result = await describe.describe(
        client, ctx, dataset_id="kzjm-xkqj", column_query=None, sample_rows=0, detail="full"
    )
    assert "gone_column" not in {f.column for f in result.place_fields or []}
    assert result.place_fields, "the pack's computed-region fields still appear"


def test_guides_module_name_has_no_dots(tmp_path):
    """Portal ids hold dots; a dotted module name breaks pickling of objects the pack defines."""
    import pickle
    import re
    import sys

    d = _pack(
        tmp_path,
        "guides.py",
        (SEATTLE / "guides.py").read_text() + "\n\ndef helper():\n    return 1\n",
    )
    ctx = load_portal(d)
    assert ctx.guides
    (name,) = [
        n for n, m in sys.modules.items() if getattr(m, "__file__", None) == str(d / "guides.py")
    ]
    assert re.fullmatch(r"[A-Za-z0-9_]+", name), name
    helper = sys.modules[name].helper
    assert pickle.loads(pickle.dumps(helper)) is helper


def _with_assertion(tmp_path, assertion, extra_evidence=""):
    text = _CLAIM_TOML.split("[[claim.assertion]]", maxsplit=1)[0] + extra_evidence + assertion
    return _pack(tmp_path, "facts/aaaa-bbbb.toml", text)


def test_assertion_params_are_validated_at_load(tmp_path):
    d = _with_assertion(
        tmp_path, '[[claim.assertion]]\nchecker = "value_present"\nparams = {x = 1}\n'
    )
    with pytest.raises(PackError, match="value_present"):
        load_portal(d)


def test_assertion_probe_index_in_range(tmp_path):
    d = _with_assertion(
        tmp_path,
        '[[claim.assertion]]\nchecker = "value_present"\nprobe = 1\n'
        'params = {column = "v", value = "-"}\n',
    )
    with pytest.raises(PackError, match="out of range"):
        load_portal(d)


def test_metadata_checker_needs_metadata_probe(tmp_path):
    d = _with_assertion(
        tmp_path,
        '[[claim.assertion]]\nchecker = "metadata_before"\n'
        'params = {field = "rowsUpdatedAt", before = 2016-01-01}\n',
    )
    with pytest.raises(PackError, match="metadata_probe"):
        load_portal(d)


def test_pack_examples_validate(tmp_path):
    paths = sorted(EXAMPLES.glob("*.toml"))
    assert len(paths) == 6
    d = tmp_path / "p"
    shutil.copytree(SEATTLE, d)
    seattle_ids = {c.id for c in load_portal(SEATTLE).pack.claims}
    for path in paths:  # the loader's own path: a stray top-level table fails here
        shutil.copy(path, d / "facts" / f"example-{path.name}")
    claims = [c for c in load_portal(d).pack.claims if c.id not in seattle_ids]
    assert {c.kind for c in claims} == set(get_args(Claim.model_fields["kind"].annotation))
    assert len(claims) == 6


def test_place_field_example_declares_its_placeholders(tmp_path):
    """The shipped place_field example's `placeholders` is a declaration (engine gap 2)."""
    d = tmp_path / "p"
    shutil.copytree(SEATTLE, d)
    shutil.copy(EXAMPLES / "place_field.toml", d / "facts" / "example-place_field.toml")
    pack = load_portal(d).pack
    assert [c.id for c in pack.placeholder_declarations("abcd-1234", "neighborhood")] == [
        "crime-neighborhood-place-field"
    ]
    assert pack.placeholders("abcd-1234", "neighborhood") == frozenset({"-"})
