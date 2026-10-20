# opendata-atlas Milestones 0–1: Feasibility Gates, Fork and Isolate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fork `seattle-open-data` into `opendata-atlas`, make every engine path take an explicit portal context with Seattle's knowledge loaded from a data pack, and run the feasibility probes that decide whether the multi-portal design holds — with Seattle behavior unchanged.

**Architecture:** The forked engine (`core/`) stops reading module-level Seattle constants. A frozen `PortalContext` (identity + knowledge pack) is built at startup from `src/opendata_atlas/portals/seattle/` and passed into every `core` entry point; caches and cursors are keyed by portal id. The MCP surface stays the four Seattle-shaped tools (renamed `atlas_*`, still Seattle-only, no `portal` argument yet — milestone 2 adds it). Feasibility probes are dev scripts whose results are recorded as facts.

**Tech Stack:** Python ≥3.12 (as `seattle-open-data`), uv, FastMCP 4 on MCP SDK v2, Pydantic, httpx, ijson, anyio; ruff, ty, prek; pytest with the forked record/replay `tests/http_fixtures.py`.

**Spec:** `docs/design.md` (with `docs/decisions.md`, `docs/upstream-facts.md`). The forked behavior's authority is `~/projects/seattle-open-data/docs/design.md` at commit `26c662858f4ef27bc5df0528e8233a80488e041e`.

**Scope note:** Milestones 2–5 get their own plans after this one lands, because milestone 0's results may change the design (the maintainer authorized the builder to adapt the design and log it, 2026-10-17). The full walk is required in milestone 2, when the surface changes.

## Global Constraints

- Fork revision: `seattle-open-data` `26c662858f4ef27bc5df0528e8233a80488e041e`. Record it in `docs/decisions.md`.
- Names: distribution `opendata-atlas`, package `opendata_atlas`, server name `opendata-atlas`, tool prefix `atlas_`, URI scheme `opendata-atlas`, error class `AtlasError`, sentinel `END OPENDATA ATLAS INSTRUCTIONS`, issues URL `https://github.com/briandconnelly/opendata-atlas/issues`.
- uv only; never pip; no `requirements.txt`. ruff, ty, prek (`uv run prek run --all-files`).
- Conventional Commits; feature branches with a type prefix; never commit to `main`. Commit trailer: `🤖 Generated with Claude Code`.
- **Seattle parity:** no warning, guide fact, or repair `seattle-open-data` emits at the fork revision is lost. In this plan the only permitted output differences are renames (tool prefix, URI scheme, server name, sentinel, issues URL) and cursor format v2 with portal binding (pre-fork cursors fail with `invalid_cursor`; Review Focus 1).
- Live tests use the `integration` marker: `uv run pytest --run-integration -m integration`.
- Record only facts you probed, except reviewer-reported facts, which are recorded with a `(review)` label.
- When a design choice changes, update `docs/design.md` and add a row to `docs/decisions.md`.
- Byte budgets: `tools/list` ≤ 24 KiB; each result ≤ 24 KiB.
- `tests/snapshots/tools_list.json` is regenerated (`UPDATE_SNAPSHOTS=1`) only in Task 1 (rename); no other task in this plan may change it.
- **Agent-facing contract standard:** the `agent-friendly-mcp` skill at `~/projects/skills/agent-friendly-mcp/`. Rule ids cited in `docs/design.md` (e.g. `[6.repair-object]`) must resolve in its `references/contract-checklist.md`. A change to the MCP surface (tools, schemas, descriptions, errors, repairs, resources, instructions, capability summary) must not violate a rule that the fork satisfied.
- **Prose standard:** every agent-consumed prose surface this plan writes or changes — server `instructions`, the capability summary, tool and resource descriptions, error messages and repair `alternative` text, `AGENTS.md`, `CLAUDE.md`, guides, and any runbook or plan an agent executes, `docs/design.md`, and this plan — is audited with the `separating-context-from-constraints` skill at `~/projects/skills/separating-context-from-constraints/`, and the task is not complete while a **Material** finding is open. Minor findings are fixed or listed in the task's commit message.

## Per-task review lenses

The reviewer of each task applies, in addition to the plan and spec:
- Any task whose diff touches the MCP surface (expected: 1, 5, 6, 10, 11): `agent-friendly-mcp`, focused route per its Checklist Map — name the sections touched, read `[1.spec-revision]` and the native-vs-convention rule, read those sections in full, close over cited rule ids, and report unread sections as `not-checked`.
- `separating-context-from-constraints`, R1–R5, reporting findings in that skill's format. The reviewer applies the separating-context-from-constraints audit to any task whose diff touches a listed prose surface. Task 2's additions to `docs/upstream-facts.md` are recorded facts, not instructions, and are exempt.

## Review Focus

1. **A cursor issued by `seattle-open-data` (or by a pre-binding build) presented to `opendata-atlas`** → `invalid_cursor` (never accepted, never a crash). Test added in Task 5.
2. **A pack claim naming a column the live schema no longer has** (the publisher dropped or renamed it) → describe and query ignore that claim for that call and still succeed; nothing raises. Test added in Task 7.
3. **A malformed or schema-invalid pack file** → the server fails at startup with an error naming the file and field, not on the first tool call. Test added in Task 4.
4. **A portal whose `timezone` is `null`** → `local_now` returns no wall-clock time and a reason (`"unknown"` or `"multi_zone"`); no exception, no UTC substitute. Test added in Task 6.
5. **Two portals sharing a region-layer id or dataset id** → cached labels, schemas and cursors never cross portals. Test added in Task 5 (the two-portal isolation regression).

---

## File Structure

```
pyproject.toml                         # forked; renamed
AGENTS.md, CLAUDE.md, README.md, CHANGELOG.md
docs/                                  # existing design docs + this plan
src/opendata_atlas/
  __init__.py
  constants.py                         # engine-wide limits only; no portal facts (Task 6)
  portals/
    __init__.py
    model.py                           # PortalIdentity, Claim, Evidence, Assertion, Pack, PortalContext (Task 4)
    loader.py                          # load_pack(dir) -> PortalContext; PackError (Task 4)
    seattle/
      portal.toml                      # Seattle identity (Task 4)
      regions.toml                     # region-layer claims (Task 7)
      facts/<dataset_id>.toml          # place-field, placeholder, time claims (Task 7)
      guides.py                        # moved from core/guides.py (Task 7)
  core/                                # forked engine; every entry point takes `portal: PortalContext`
    cache.py, catalog.py, context.py, cursor.py, describe.py, http.py, query.py, reference.py, ...
  mcp/                                 # forked; builds the Seattle context at startup (Task 8)
scripts/feasibility/
  enumerate_domains.py                 # Task 2
  check_identity.py                    # Task 2
  check_token.py                       # Task 2
  budget_spike.py                      # Task 9
  compat_run.py                        # Task 9
evals/run.py                           # forked; tools restricted (Task 10)
tests/                                 # forked; plus test_portal_model.py, test_packs.py,
                                       # test_isolation.py, test_feasibility.py
```

---

### Task 1: Fork and rename

**Files:**
- Create: everything under the repo root from `git -C ~/projects/seattle-open-data archive 26c6628` (excluding `docs/`, `evals/results/`, `.git`)
- Modify: `pyproject.toml`, `src/opendata_atlas/constants.py`, `src/opendata_atlas/core/errors.py`, `manifest.json`, `server.json` (if present), `AGENTS.md`, `README.md`, `CHANGELOG.md`, `tests/snapshots/tools_list.json`, `docs/decisions.md`

**Interfaces:**
- Produces: package `opendata_atlas` with the forked module layout; `AtlasError` (renamed `SeattleDataError`, same constructor); tools `atlas_search_datasets`, `atlas_describe_dataset`, `atlas_query_dataset`, `atlas_get_reference`; URI scheme `opendata-atlas://`.

- [ ] **Step 1: Branch and import the fork**

```bash
cd ~/projects/opendata-atlas && git checkout -b feat/fork-and-isolate docs/design
git -C ~/projects/seattle-open-data archive 26c662858f4ef27bc5df0528e8233a80488e041e \
  | tar -x --exclude='docs' --exclude='evals/results' -C .
git add -A && git commit -m "chore: import seattle-open-data at 26c6628

🤖 Generated with Claude Code"
```

- [ ] **Step 2: Rename mechanically**

`git mv src/seattle_open_data src/opendata_atlas`, then replace across `src tests scripts evals pyproject.toml manifest.json AGENTS.md README.md`:
`seattle_open_data`→`opendata_atlas`, `seattle-open-data`→`opendata-atlas` (server name, distribution, issues URL), `seattle_data_`→`atlas_`, `seattle-data://`→`opendata-atlas://`, `SeattleDataError`→`AtlasError`, `END SEATTLE OPEN DATA INSTRUCTIONS`→`END OPENDATA ATLAS INSTRUCTIONS`. Leave prose that is about Seattle the city (guides, facts) unchanged. `AGENTS.md`: keep its rules; point design references at this repo's `docs/`.

- [ ] **Step 3: Run the full suite; only snapshot and name-pinning tests may fail**

Run: `uv sync && uv run pytest -q`
Expected: failures only in `tests/test_contract.py` (snapshot) and any test asserting literal old names.

- [ ] **Step 4: Regenerate the snapshot (the one permitted regeneration) and fix literal-name assertions**

Run: `UPDATE_SNAPSHOTS=1 uv run pytest tests/test_contract.py -q && uv run pytest -q`
Expected: all pass. `git diff --stat tests/snapshots/tools_list.json` shows name changes only (inspect it).

- [ ] **Step 5: Gate**

Run: `uv run ruff check && uv run ruff format --check && uv run ty check && uv run prek run --all-files`
Expected: clean.

- [ ] **Step 6: Record the fork and commit**

Add to `docs/decisions.md` log: `| Fork | — | Forked from seattle-open-data 26c662858f4ef27bc5df0528e8233a80488e041e; renamed | Milestone 1 |`. Fork upkeep (design: Constraints): list every `seattle-open-data` commit after `26c6628` (`git -C ~/projects/seattle-open-data log --oneline 26c6628..main`) in the PR description as candidates for `port` issues, to be filed once this repo is on GitHub. Filing them is outside this plan. CHANGELOG `## [Unreleased]`: "Forked from seattle-open-data; renamed to opendata-atlas (tool prefix `atlas_`)."

```bash
git add -A && git commit -m "refactor: rename fork to opendata-atlas

🤖 Generated with Claude Code"
```

---

### Task 2: Feasibility probes — enumeration, eligibility, identity, token (milestone 0a)

**Files:**
- Create: `scripts/feasibility/enumerate_domains.py`, `scripts/feasibility/check_identity.py`, `scripts/feasibility/check_token.py`, `tests/test_feasibility.py`
- Modify: `docs/upstream-facts.md`, and `docs/design.md` + `docs/decisions.md` if a gate fails

**Interfaces:**
- Produces (pure functions, reused by milestone 2's registry generator):
  - `is_eligible(domain: str) -> bool` in `scripts/feasibility/enumerate_domains.py` — false for `*.demo.socrata.com`, `internal*`, `priv-*`, and any `*.socrata.com` subdomain.
  - `identity_matches(pages: list[list[dict]], expected_domain: str) -> bool` in `scripts/feasibility/check_identity.py` — true only when there are ≥1 non-empty pages and every result's `metadata.domain == expected_domain`.

- [ ] **Step 1: Write failing tests for the pure functions**

```python
def test_is_eligible_rejects_demo_internal_and_socrata_subdomains():
    assert not is_eligible("mesa-az.demo.socrata.com")
    assert not is_eligible("internal-sandiegocounty.data.socrata.com")
    assert not is_eligible("priv-data.ojp.usdoj.gov")
    assert not is_eligible("albany.data.socrata.com")
    assert is_eligible("data.cityofchicago.org")


def test_identity_matches_requires_every_result_on_expected_domain():
    ok = [[{"metadata": {"domain": "data.sf.gov"}}] * 3] * 3
    mixed = [[{"metadata": {"domain": "data.sf.gov"}}, {"metadata": {"domain": "data.sfgov.org"}}]]
    assert identity_matches(ok, "data.sf.gov")
    assert not identity_matches(mixed, "data.sf.gov")
    assert not identity_matches([], "data.sf.gov")
    assert not identity_matches([[]], "data.sf.gov")
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_feasibility.py -v` — Expected: FAIL (import error).

- [ ] **Step 3: Implement the pure functions and the three CLIs**

- `enumerate_domains.py`: try, in order, and record which works: (a) `GET {region}/api/catalog/v1/domains` (both `api.us.socrata.com` and `api.eu.socrata.com`); (b) paging `GET {region}/api/catalog/v1?only=dataset&limit=10000&offset=N` collecting `metadata.domain`, recording the offset at which paging stops (the catalog reported `resultSetSize` 10,000 for the EU region with `limit=0`, so a cap is likely); (c) faceted search per topic word as a fallback. Prints `{method, regions, domain_count, eligible_count, capped: bool}` as JSON plus the eligible domain list to a file argument.
- `check_identity.py <host...>`: for each host, fetch the first three pages (`limit=100`) with `domains=<host>`, then `search_context=<host>`, and with each catalog `link` host seen on the first page; report which params satisfy `identity_matches`, plus `GET https://<host>/api/views.json?limit=1` status (anonymous `/api/views` eligibility). Also issue one `/resource/<id>.json?$limit=1` for the first dataset id to confirm query routing on the public host.
- `check_token.py <host...>`: with `SOCRATA_APP_TOKEN` set, request `/resource/<id>.json?$limit=1` on each host with the token; record status per host. If no token is available, print `token: unavailable` and exit 0.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_feasibility.py -v` — Expected: PASS.

- [ ] **Step 5: Run the probes on the 20-portal sample**

Sample (fixed): `data.seattle.gov`, `data.sf.gov`, `data.cityofchicago.org`, `data.cityofnewyork.us`, `data.kingcounty.gov`, `datahub.austintexas.gov`, `www.dallasopendata.com`, `data.lacity.org`, `data.nola.gov`, `datacatalog.cookcountyil.gov`, `data.montgomerycountymd.gov`, `data.wa.gov`, `data.ny.gov`, `data.texas.gov`, `data.cdc.gov`, `data.calgary.ca`, `www.datos.gov.co`, `data.oregon.gov`, `data.honolulu.gov`, and one EU-region domain found by `enumerate_domains.py`.

Run: `uv run python scripts/feasibility/enumerate_domains.py /tmp/domains.json`, `uv run python scripts/feasibility/check_identity.py <sample...>`, `uv run python scripts/feasibility/check_token.py <sample...>`
Expected: JSON outputs saved; no crash.

- [ ] **Step 6: Record facts and decide the gates**

Write each result to `docs/upstream-facts.md` as **Verified** with the command and date. Gate decisions, each logged in `docs/decisions.md`:
- Enumeration: if no method yields an uncapped list, adopt the fallback: registry = enumeration ∪ `registry_overrides.toml`, and change the design's promise to "every portal in the registry" (README and capability text in milestone 2).
- Identity: `catalog_query` (exact Discovery parameters; see Task 4) is adopted unconditionally, whatever the gate shows, because Seattle already needs two Discovery parameters at once (`domains` + `search_context`). The gate result is recorded either way; log the adoption in `docs/decisions.md`, and update `docs/design.md`'s identity table (`catalog_param` → `catalog_query`) in Task 4.
- Token: if any host rejects a token another accepts, adopt `SOCRATA_APP_TOKENS` (host→token map) for milestone 2.

- [ ] **Step 7: Commit**

```bash
git add scripts/feasibility tests/test_feasibility.py docs
git commit -m "feat: add milestone 0 feasibility probes and record results

🤖 Generated with Claude Code"
```

---

### Task 3: Move portal facts out of `constants.py` (no behavior change)

**Files:**
- Modify: `src/opendata_atlas/constants.py`
- Create: `src/opendata_atlas/portals/__init__.py`, `src/opendata_atlas/portals/seattle_legacy.py`

**Interfaces:**
- Produces: `opendata_atlas.portals.seattle_legacy` holding exactly `PUBLIC_HOST`, `CATALOG_DOMAIN`, `SEATTLE_TZ`, `PLACEHOLDER_VALUES`, `REGION_LAYERS`, `PLACE_FIELDS`, `TIME_EVIDENCE` (moved verbatim). `constants.py` keeps only engine-wide limits, `DISCOVERY_API`, `GEO_TYPES`, `TIME_TYPES`, and names. This is a staging module deleted in Task 7.

- [ ] **Step 1: Move the seven names; update the six importing modules to import them from `portals.seattle_legacy`**
- [ ] **Step 2: Verify nothing else references them in `constants`**

Run: `grep -rnE "constants import.*(PUBLIC_HOST|CATALOG_DOMAIN|SEATTLE_TZ|PLACEHOLDER_VALUES|REGION_LAYERS|PLACE_FIELDS|TIME_EVIDENCE)" src tests` — Expected: no output.

- [ ] **Step 3: Full suite and gate**

Run: `uv run pytest -q && uv run ty check && uv run ruff check` — Expected: all pass, snapshot unchanged.

- [ ] **Step 4: Commit** — `refactor: stage Seattle portal facts outside engine constants`

---

### Task 4: Portal model, pack loader, Seattle identity

**Files:**
- Create: `src/opendata_atlas/portals/model.py`, `src/opendata_atlas/portals/loader.py`, `src/opendata_atlas/portals/seattle/portal.toml`, `tests/test_portal_model.py`, `tests/test_packs.py`
- Modify: `pyproject.toml` (package data: include `portals/**/*.toml`), `docs/design.md` (identity table: `catalog_param` → `catalog_query`)

**Interfaces:**
- Produces, in `portals/model.py` (Pydantic, `extra="forbid"` everywhere):
  - `Jurisdiction(level: Literal["city","county","region","state","national","other"], country: str, region: str | None)`
  - `PortalIdentity(id: str, aliases: list[str], public_host: str, catalog_query: dict[str, str], catalog_region: Literal["us","eu"], name: str, place_names: list[str], jurisdiction: Jurisdiction | None, timezone: str | None, platform: Literal["socrata"], status: Literal["active","retired"])` — `id` pattern `^[a-z0-9][a-z0-9.-]{1,99}$`; each alias pattern `^[a-z0-9][a-z0-9-]{1,39}$`; `timezone` must be a valid `zoneinfo` key when set. `catalog_query` replaces the design's `catalog_param` (adopted unconditionally; see Task 2 Step 6): the exact Discovery parameters that select the portal; Seattle's is `{"domains": "cos-data.seattle.gov", "search_context": "data.seattle.gov"}`, which is what the fork sends today. Add `catalog_domain` as a computed property: `catalog_query.get("domains") or public_host`.
  - `Evidence` (discriminated on `kind`): `SoqlProbe(kind="soql_probe", query: str, observed_at: date, observation: str)`, `MetadataProbe(kind="metadata_probe", path: str, observed_at: date, observation: str)`, `Document(kind="document", url: str, quote: str, observed_at: date)`, `ManualObservation(kind="manual_observation", note: str, observed_at: date)`.
  - `Assertion(checker: str, params: dict[str, Any])` — typed checker params arrive in milestone 3.
  - `Scope(dataset: str | None, column: str | None, layer: str | None, time: dict[str, str] | None)`
  - `Interpretation(reliability: Literal["ok","partial","unreliable"] | None, reason: str | None, kind: str | None, kind_label: str | None, timezone: str | None, label_column: str | None, vintage: str | None)`
  - `Claim(id: str, kind: Literal["place_field","region_layer","placeholder_share","column_timezone","unit_of_observation"], scope: Scope, interpretation: Interpretation | None, placeholders: list[str] | None, reviewed_by: str | None, reviewed_at: date | None, evidence: list[Evidence], assertion: list[Assertion])` — validator: an `interpretation` requires `reviewed_by` and `reviewed_at`; `evidence` non-empty.
  - `Pack(claims: list[Claim])` with lookup methods `place_fields(dataset_id) -> dict[str, Claim]`, `region_layer(layer_id) -> Claim | None`, `column_timezone(dataset_id, column) -> Claim | None`, `placeholders(dataset_id, column) -> frozenset[str]` (empty when undeclared).
  - `PortalContext` — `@dataclass(frozen=True)`: `identity: PortalIdentity`, `pack: Pack`, `guides: tuple[Guide, ...]`; property `id -> str`; property `tz -> ZoneInfo | None`.
- Produces, in `portals/loader.py`: `class PackError(Exception)` (message names file and field); `load_portal(directory: Path) -> PortalContext` reading `portal.toml`, `regions.toml` (optional), `facts/*.toml` (optional), and `guides.py` (optional, attribute `GUIDES`); `SEATTLE: Path` constant for the packaged Seattle directory.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_portal_model.py
def test_seattle_identity_loads():
    ctx = load_portal(SEATTLE)
    assert ctx.id == "data.seattle.gov"
    assert ctx.identity.aliases == ["seattle"]
    assert ctx.identity.catalog_query == {
        "domains": "cos-data.seattle.gov",
        "search_context": "data.seattle.gov",
    }
    assert ctx.identity.catalog_domain == "cos-data.seattle.gov"
    assert str(ctx.tz) == "America/Los_Angeles"


def test_interpretation_requires_reviewer():
    with pytest.raises(ValidationError):
        Claim(
            id="x",
            kind="place_field",
            scope=Scope(dataset="aaaa-bbbb", column="c"),
            interpretation=Interpretation(reliability="ok"),
            evidence=[
                ManualObservation(
                    kind="manual_observation", note="n", observed_at=date(2026, 10, 17)
                )
            ],
            assertion=[],
        )


def test_bad_timezone_and_alias_rejected():
    for bad in ({"timezone": "Pacific/Nowhere"}, {"aliases": ["Seattle WA"]}):
        with pytest.raises(ValidationError):
            PortalIdentity(**(SEATTLE_IDENTITY_DICT | bad))


# tests/test_packs.py  (Review Focus 3)
def test_malformed_pack_fails_at_load_naming_file(tmp_path):
    shutil.copytree(SEATTLE, tmp_path / "p")
    (tmp_path / "p" / "portal.toml").write_text('id = "data.seattle.gov"\ntimezone = 7\n')
    with pytest.raises(PackError, match=r"portal\.toml.*timezone"):
        load_portal(tmp_path / "p")


def test_every_shipped_pack_loads():
    for d in PORTALS_DIR.iterdir():
        if (d / "portal.toml").exists():
            load_portal(d)
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_portal_model.py tests/test_packs.py -v` → FAIL (import error).
- [ ] **Step 3: Implement `model.py`, `loader.py`, and `seattle/portal.toml`** (identity values: name `City of Seattle`, place_names `["Seattle", "Seattle, WA"]`, jurisdiction `{level="city", country="US", region="WA"}`, `catalog_region="us"`, `status="active"`, `platform="socrata"`). Use `tomllib`; wrap `ValidationError`/`TOMLDecodeError` in `PackError(f"{path}: {field}: {msg}")`.
- [ ] **Step 4: Run tests** — expected PASS. Full suite still passes.
- [ ] **Step 5: Commit** — `feat: add portal identity, claim model, and pack loader`

---

### Task 5: Thread `PortalContext` through http, catalog, cache and cursor; isolation regression

**Files:**
- Modify: `core/http.py`, `core/catalog.py`, `core/cache.py`, `core/cursor.py`, `core/query.py`, `core/describe.py`, `mcp/tools.py`, `mcp/server.py`, `tests/conftest.py`
- Create: `tests/test_isolation.py`

**Interfaces:**
- Consumes: `PortalContext` (Task 4).
- Produces:
  - `SodaClient` methods gain a leading `portal: PortalContext` parameter wherever they build a URL; URLs use `portal.identity.public_host`.
  - `catalog.search(client, portal, ...)`; Discovery base URL from `portal.identity.catalog_region` (`https://api.{region}.socrata.com/api/catalog/v1`); params from `portal.identity.catalog_query`; `public_url` rewrites `portal.identity.catalog_domain` → `public_host`.
  - `cache.views: TtlCache[tuple[str, str], dict]` keyed `(portal.id, dataset_id)`; `cache.region_labels: TtlCache[tuple[str, str, str], str]` keyed `(portal.id, layer_id, feature_id)`; `cached_view(client, portal, dataset_id)`, `fresh_view(client, portal, dataset_id)`.
  - Cursor: `encode(kind: str, state: dict[str, Any], *, portal_id: str) -> str` stores `"p": portal_id`; `_VERSION` becomes `2`; `decode(cursor: str, kind: str, *, portal_id: str, restart: Repair) -> dict[str, Any]` raises `invalid_cursor` (with the existing `restart` repair) when the version is not 2, or `"p"` is missing or differs from `portal_id`.
  - `describe.describe(client, portal, *, dataset_id, ...)`, `query.run(client, portal, *, dataset_id, ...)`.
  - `mcp/server.py` builds `SEATTLE_CONTEXT = load_portal(SEATTLE)` once at startup and the tool handlers pass it (no `portal` argument yet).

- [ ] **Step 1: Write the failing isolation regression (Review Focus 5) and cursor test (Review Focus 1)**

```python
# tests/test_isolation.py
async def test_same_dataset_id_on_two_portals_never_shares_state(two_portals, replay):
    """Portal A and B both serve aaaa-bbbb with different schemas and region labels."""
    a, b = two_portals  # PortalContext for a.example.gov and b.example.gov (fixture packs)
    da = await describe.describe(client, a, dataset_id="aaaa-bbbb", detail="full")
    db = await describe.describe(client, b, dataset_id="aaaa-bbbb", detail="full")
    assert [c.name for c in da.columns] == ["alpha"]
    assert [c.name for c in db.columns] == ["beta"]
    assert {f.column for f in da.place_fields or []} != {f.column for f in db.place_fields or []}
    qa = await query.run(client, a, dataset_id="aaaa-bbbb", page_size=1)
    with pytest.raises(AtlasError) as err:
        await query.run(client, b, dataset_id="aaaa-bbbb", cursor=qa.next_cursor)
    assert err.value.code == "invalid_cursor"


def test_version1_cursor_rejected():
    legacy = _encode_v1(
        "query", {"dataset_id": "kzjm-xkqj"}
    )  # helper reproducing the fork's v1 format
    with pytest.raises(AtlasError) as err:
        cursor.decode(
            legacy, "query", portal_id="data.seattle.gov", restart=READ_PAGING
        )  # READ_PAGING: the fork's paging-reference repair
    assert err.value.code == "invalid_cursor"
```

Fixtures: two minimal packs under `tests/fixtures/portals/{a,b}/` and recorded responses for both hosts in `tests/fixtures/` using the existing `http_fixtures` replay format. Portal A's region layer `cccc-dddd` labels feature `1` as `NORTH`; B's labels it `SOUTH`; assert the labels differ.

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_isolation.py -v` → FAIL (signatures).
- [ ] **Step 3: Thread the context** through the listed modules per the Interfaces block; replace every `PUBLIC_HOST`/`CATALOG_DOMAIN` use with the portal's identity.
- [ ] **Step 4: Run isolation tests, then the full suite** — `uv run pytest -q` → all pass (existing tests unchanged from the fork revision except mechanical `portal` threading at call sites); `git diff --quiet tests/snapshots/tools_list.json` succeeds (unchanged).
- [ ] **Step 5: Commit** — `feat: key engine state by portal and bind cursors to it`

---

### Task 6: Portal timezone in `source`

**Files:**
- Modify: `core/context.py`, `core/models.py` (the `Source` model), callers of `make_source`
- Test: `tests/test_portal_model.py`

**Interfaces:**
- Produces:
  - `local_now(portal: PortalContext, now: datetime) -> tuple[str | None, Literal["multi_zone", "unknown"] | None]` in `core/context.py`: ISO 8601 with UTC offset, `isoformat(timespec="seconds")` on the zone-aware time (the fork's format), and `None`, or `(None, reason)` when `portal.tz` is `None`. `reason` is `"multi_zone"` when `jurisdiction.level` is `state` or `national`, otherwise `"unknown"`.
  - `make_source(portal: PortalContext, *, retrieved: bool = False) -> Source` uses `local_now`. **`Source` is unchanged in this plan:** it is in the pinned output schema and nested output objects are closed, so `now_local_reason` and `source.portal` ship together in milestone 2. Every portal in this plan (Seattle) has a timezone, so `Source.now_local` stays non-null.

- [ ] **Step 1: Failing tests (Review Focus 4)**

```python
NOW = datetime(2026, 10, 17, 19, 0, tzinfo=UTC)


def test_null_timezone_gives_reason_not_utc():
    ctx = with_identity(load_portal(SEATTLE), timezone=None)
    assert local_now(ctx, NOW) == (None, "unknown")
    state = with_identity(ctx, jurisdiction={"level": "state", "country": "US", "region": "TX"})
    assert local_now(state, NOW) == (None, "multi_zone")


def test_seattle_local_now_is_pacific_wall_clock():
    # Same format as the fork's make_source: isoformat(timespec="seconds") on an aware datetime.
    assert local_now(load_portal(SEATTLE), NOW) == ("2026-10-17T12:00:00-07:00", None)
```

Test helpers `with_identity(ctx, **updates) -> PortalContext` and `with_extra_claim(ctx, *, dataset, column, reliability) -> PortalContext` live in `tests/conftest.py` (built with `dataclasses.replace` and `model_copy(update=...)`); Task 7 reuses `with_extra_claim`.

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run → PASS; full suite passes; `git diff --quiet tests/snapshots/` succeeds.**

- [ ] **Step 5: Commit** — `feat: derive now_local from the portal timezone`

---

### Task 7: Seattle knowledge as a pack; engine reads it

**Files:**
- Create: `src/opendata_atlas/portals/seattle/regions.toml`, `src/opendata_atlas/portals/seattle/facts/{33kz-ixgy,tazs-3rd5,ppi5-g2bj,76t5-zqzr,kzjm-xkqj,65db-xm6k}.toml`
- Move: `core/guides.py` → `portals/seattle/guides.py` (keep `Guide`/`Example` classes in `core/guides.py`; move only `GUIDES` data)
- Delete: `portals/seattle_legacy.py`
- Modify: `core/describe.py` (`place_specs`, `_coverage_columns`, `_time`, `_place_field`), `core/query.py` (warnings), `core/catalog.py` (`_guide_uri`), `core/reference.py` (guide documents), `mcp/resources.py`
- Test: `tests/test_packs.py`; existing describe/query tests unchanged from the fork revision except mechanical `portal` threading at call sites

**Interfaces:**
- Consumes: `Pack` lookups and `PortalContext.guides` (Task 4).
- Produces: `place_specs(portal, dataset_id, columns)`; `_time(portal, dataset_id, column)`; `_coverage_columns(portal, dataset_id, time_columns)`; guide lookup `portal.guides` with `BY_DATASET`/`BY_ID` built per context.

Conversion rules (verbatim values from `seattle_legacy.py`, evidence from `docs/upstream-facts.md` in the Seattle repo at the fork revision):
- Each `REGION_LAYERS` entry → one `kind="region_layer"` claim, `scope.layer=<id>`, interpretation `{kind, label_column, vintage, reliability, reason}`, one `MetadataProbe` evidence citing the layer's `rowsUpdatedAt` observation.
- Each `PLACE_FIELDS` column → one `kind="place_field"` claim with `{kind, reliability, reason}` and `placeholders = sorted(PLACEHOLDER_VALUES)` (the fork applies the full vocabulary to every text place field; declaring it per column keeps parity).
- Each `TIME_EVIDENCE` column → one `kind="column_timezone"` claim, interpretation `{timezone}`, `ManualObservation` evidence with the recorded evidence string.
- `reviewed_by = "claude"`, `reviewed_at` = the probe date recorded in Seattle's facts; `assertion = []` (checkers arrive in milestone 3).
- Unreviewed computed-region layers keep the fork's behavior: `kind: "other"`, `reliability: "partial"` (`core/describe.py:264` at the fork revision).

- [ ] **Step 1: Failing tests**

```python
def test_seattle_pack_reproduces_legacy_facts():
    pack = load_portal(SEATTLE).pack
    assert pack.place_fields("tazs-3rd5")["neighborhood"].interpretation.reliability == "partial"
    assert pack.region_layer("cyqu-gs94").interpretation.reliability == "unreliable"
    assert (
        pack.column_timezone("33kz-ixgy", "cad_event_original_time_queued").interpretation.timezone
        == "America/Los_Angeles"
    )
    assert pack.placeholders("33kz-ixgy", "dispatch_neighborhood") == frozenset(
        {"-", "UNKNOWN", "NULL", "OOJ", "FK ERROR", "X", "0", ""}
    )
    assert pack.placeholders("33kz-ixgy", "not_a_place_field") == frozenset()


async def test_claim_for_missing_column_is_ignored(replay):  # Review Focus 2
    ctx = with_extra_claim(
        load_portal(SEATTLE), dataset="kzjm-xkqj", column="gone_column", reliability="ok"
    )
    result = await describe.describe(client, ctx, dataset_id="kzjm-xkqj", detail="full")
    assert "gone_column" not in {f.column for f in result.place_fields or []}
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Write the pack files and switch the engine reads**; `describe._place_field` excludes values only from `portal.pack.placeholders(dataset_id, column)` (empty for computed-region fields, as today); claims whose column is absent from the live schema are skipped.
- [ ] **Step 4: Parity check** — `uv run pytest -q` → all existing describe/query/guide/repair tests pass unchanged from the fork revision except mechanical `portal` threading at call sites; `git diff --quiet tests/snapshots/` succeeds. Run `grep -rn seattle_legacy src tests` → no output.
- [ ] **Step 5: Commit** — `feat: load Seattle knowledge from a data pack`

---

### Task 8: No engine reads of Seattle outside the pack (guard test)

**Files:**
- Create: `tests/test_no_portal_constants.py`

**Interfaces:**
- Consumes: the finished Tasks 5–7.

- [ ] **Step 1: Write the guard**

```python
FORBIDDEN = re.compile(r"seattle\.gov|cos-data|America/Los_Angeles|kzjm-xkqj|33kz-ixgy|tazs-3rd5")


def test_engine_has_no_portal_literals():
    hits = [
        f"{p}:{n}"
        for p in (ROOT / "src/opendata_atlas/core").rglob("*.py")
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert hits == []
```

- [ ] **Step 2: Run** — expected PASS if Tasks 5–7 are complete; on failure, move each hit into the Seattle pack or behind `PortalContext`. Also run the guard against a known positive (temporarily add `# seattle.gov` to a core file, confirm FAIL, revert).
- [ ] **Step 3: Commit** — `test: guard the engine against portal literals`

---

### Task 9: Feasibility after the fork — budget spike and cross-portal compatibility (milestone 0b)

**Files:**
- Create: `scripts/feasibility/budget_spike.py`, `scripts/feasibility/compat_run.py`
- Modify: `docs/upstream-facts.md`, `docs/decisions.md`, `docs/design.md`

**Interfaces:**
- Consumes: `load_portal`, `PortalIdentity`, `PortalContext`, `catalog.search`, `describe.describe`, `query.run` (Tasks 4–7).
- Produces: `build_context(host: str, catalog_query: dict[str, str]) -> PortalContext` in `compat_run.py` — an empty-pack context for a probed host.

- [ ] **Step 1: Budget spike.** `budget_spike.py` loads the current `tools/list` (via the in-process server), adds a required `portal` string property (pattern `^[A-Za-z0-9][A-Za-z0-9.-]{1,99}$`, description ≤ 200 bytes) to the four tools' input schemas, adds a fifth tool `atlas_find_portals` whose input/output schema is written per `docs/design.md` (Tools §1) with descriptions at Seattle's density, and prints the total serialized bytes. Gate: ≤ 24,576 bytes. If over, log the overage and the trims chosen in `docs/decisions.md`.
- [ ] **Step 2: Compatibility run.** `compat_run.py` takes Task 2's identity results; for each of the 20 sample portals it runs `search` (one query: `"permits"`), `describe` (first tabular result, `detail="full"`), `query` (two pages via cursor), and one forced error (`query` with `select=["no_such_column_xyz"]`, expecting `no_such_column`). Prints a table: host, each step's outcome (`ok | <error code>`), elapsed seconds.
- [ ] **Step 3: Run both** — `uv run python scripts/feasibility/budget_spike.py`, `uv run python scripts/feasibility/compat_run.py <identity.json>`; save outputs.
- [ ] **Step 4: Record and decide.** Each portal result → `docs/upstream-facts.md` (Verified, dated). Any step failing on ≥ 1 portal for a reason other than that portal's data (e.g. a shape the engine does not handle) → a row in `docs/decisions.md` and an issue `gap: <summary>` for milestone 2's plan. Reword `docs/design.md`'s Intent item 1 (Reach) and the Goals line "One server, one install, any registered portal" to say generic behavior on every registered portal is a goal verified by milestone 2's compatibility suite.
- [ ] **Step 5: Commit** — `feat: add budget spike and cross-portal compatibility run`

---

### Task 10: Eval runner restricted to server tools; Seattle parity eval

**Files:**
- Modify: `evals/run.py`, `evals/results/` (new file), `docs/design.md` (Evals: record the run), `CHANGELOG.md`

**Interfaces:**
- Consumes: the renamed server (Task 1) and finished isolation (Tasks 5–8).

- [ ] **Step 1: Restrict tools.** In `claude_command`, add `"--tools", ""` before `--allowedTools`, and change `TOOLS` to the `atlas_*` names. Codex path unchanged (its clean `CODEX_HOME` already removes other tools).
- [ ] **Step 2: Known-positive check of the restriction.** Run `uv run python evals/run.py /tmp/atlas-eval 03-fire-capitol-hill`; read `03-fire-capitol-hill.transcript.jsonl`'s `system/init` event: `tools` must list only `mcp__opendata-atlas__atlas_*` names, and no `tool_use` may name a non-MCP tool.
- [ ] **Step 3: Full run.** `uv run python evals/run.py evals/results/2026-MM-DD-fork` (all 24 tasks).
- [ ] **Step 4: Grade against the baseline.** Grade each task PASS/PARTIAL/FAIL against `expect` (substance, not field names). Baseline: the 2026-10-17 restricted run of `seattle-open-data` (23 PASS, 1 PARTIAL — `15-ballard-911`). Gate: no task grades lower than its baseline grade; first-call correctness ≥ 95%, first-repair ≥ 90%, zero silent completeness, coverage or timezone errors. A lower grade on any task blocks completion until one re-run, or a fix, grades that task at or above its baseline.
- [ ] **Step 5: Record and commit.** Write `evals/results/<date>-fork.md` (table, totals, baseline comparison). CHANGELOG `## [Unreleased]`: "Eval runner restricts the agent to the server's tools (`--tools \"\"`)." Commit — `test: restrict eval runner to server tools and record fork parity run`.

---

### Task 11: Standards review of the branch

**Files:**
- Create: `docs/reviews/2026-MM-DD-m1-standards.md`
- Modify: whatever the findings require; `docs/decisions.md`

**Interfaces:**
- Consumes: the finished branch (Tasks 1–10).

- [ ] **Step 1: agent-friendly-mcp review.** Follow the skill's `references/review-workflow.md`. Route: **focused**, because the surface is the fork's (already reviewed in `seattle-open-data`) plus renames and cursor binding; name sections §1 (identity), §2 (instructions, capability summary), §3 (tool names, descriptions), §6 (the `invalid_cursor` path for pre-fork and cross-portal cursors), §8 (cursor), §9 (versioning: a renamed server is a new server; its version starts at `0.1.0`, and the CHANGELOG says it is a fork). Close over cited ids; escalate to the full walk if closure pulls in more than two further sections, per the skill. Record every section as finding / `OK` with evidence / `not-checked` with reason.
- [ ] **Step 2: separating-context-from-constraints audit** of: server `instructions` (as served), the capability summary, the four tool descriptions, the error catalog's `alternative` texts, `AGENTS.md`, `CLAUDE.md`, and this plan's Global Constraints section. Report in the skill's finding and summary formats.
- [ ] **Step 3: Fix** every Material finding from both reviews (with a regression test where the finding is about behavior), and fix or list Minor ones. Re-run `uv run pytest -q` and the gate from Task 1 Step 5.
- [ ] **Step 4: Record** both reports in `docs/reviews/2026-MM-DD-m1-standards.md` and add a `docs/decisions.md` row summarizing what changed. Commit — `docs: record milestone 1 standards review`.

## Done criteria for this plan

- `uv run pytest -q`, `uv run ty check`, `uv run ruff check`, `uv run prek run --all-files` clean; `uv run pytest --run-integration -m integration` passes.
- `tests/snapshots/tools_list.json` changed only in Task 1.
- Feasibility results for enumeration, identity, token, budget and compatibility are in `docs/upstream-facts.md`, and every gate decision is a row in `docs/decisions.md`.
- Seattle parity eval meets the Task 10 gate.
- Task 11's reviews are recorded with no open Material finding.

**Next:** plan milestone 2 (portal surface) from the updated design.
