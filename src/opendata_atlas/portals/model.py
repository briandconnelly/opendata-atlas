"""Portal identity and knowledge-pack model (docs/design.md: Portal model)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date  # noqa: TC003 (pydantic resolves field types at runtime)
from functools import cached_property
from typing import TYPE_CHECKING, Annotated, Any, Literal, get_args
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from opendata_atlas.portals.checkers import CHECKERS, CheckerName

if TYPE_CHECKING:
    from collections.abc import Mapping

    from opendata_atlas.core.guides import Guide
    from opendata_atlas.portals.validation import ClaimCheck

PlaceKind = Literal[
    "neighborhood",
    "precinct",
    "sector",
    "beat",
    "zip",
    "council_district",
    "census_tract",
    "ward",
    "community_area",
    "borough",
    "community_district",
    "county",
    "police_district",
    "school_district",
    "other",
]
#: How much is known about a dataset or column (docs/design.md: Knowledge levels).
KnowledgeLevel = Literal["none", "profiled", "reviewed"]
#: What a claim's assertions last said, aged by the runtime freshness rule (`freshness.py`).
Validation = Literal["unchecked", "passed", "stale", "contradicted", "inconclusive"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_zone(v: str | None) -> str | None:
    if v is not None:
        try:
            ZoneInfo(v)
        except (ValueError, KeyError, OSError) as e:
            raise ValueError(f"unknown timezone {v!r}") from e
    return v


class Jurisdiction(_Strict):
    level: Literal["city", "county", "region", "state", "national", "other"]
    country: str
    region: str | None = None


class PortalIdentity(_Strict):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9.-]{1,99}$")
    aliases: list[Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,39}$")]] = []
    public_host: str
    catalog_query: dict[str, str]
    catalog_region: Literal["us", "eu"]
    name: str
    place_names: list[str] = []
    jurisdiction: Jurisdiction | None = None
    timezone: str | None = None
    platform: Literal["socrata"]
    status: Literal["active", "retired"]
    tier: Literal["generic", "profiled", "curated"]

    @field_validator("timezone")
    @classmethod
    def _valid_zone(cls, v: str | None) -> str | None:
        return _check_zone(v)

    @field_validator("catalog_query")
    @classmethod
    def _names_a_domain(cls, v: dict[str, str]) -> dict[str, str]:
        if not (v.get("domains") or v.get("search_context")):
            raise ValueError("catalog_query needs `domains` or `search_context`")
        return v

    @property
    def catalog_domain(self) -> str:
        """The name the Discovery API indexes this portal under (the `domains=` value).

        Also the host catalog links use, rewritten to `public_host`. Never compare results
        against it; use `result_domain`.
        """
        return self.catalog_query.get("domains") or self.public_host

    @property
    def result_domain(self) -> str:
        """The `metadata.domain` every catalog entry of this portal carries.

        Unlike `catalog_domain` (the indexing name and link host), this is what results are
        compared against.
        `search_context` rewrites result domains, so it wins over `domains`; this is the
        rule scripts/build_registry.py `expected_domain` accepted each entry on.
        """
        return self.catalog_query.get("search_context") or self.catalog_query["domains"]


class SoqlProbe(_Strict):
    kind: Literal["soql_probe"]
    query: str
    observed_at: date
    observation: str


class MetadataProbe(_Strict):
    kind: Literal["metadata_probe"]
    #: A path on the portal's public host.
    path: str = Field(pattern=r"^/api/")
    observed_at: date
    observation: str


class Document(_Strict):
    kind: Literal["document"]
    url: str
    quote: str
    observed_at: date


class ManualObservation(_Strict):
    kind: Literal["manual_observation"]
    note: str
    observed_at: date


Evidence = Annotated[
    SoqlProbe | MetadataProbe | Document | ManualObservation, Field(discriminator="kind")
]


class Assertion(_Strict):
    """One check over a claim's probe evidence, with params typed by its checker."""

    checker: CheckerName
    #: Index into `Claim.probes` (the probe evidence, in evidence order), not `Claim.evidence`.
    probe: int = Field(default=0, ge=0)
    params: dict[str, Any] = {}

    @model_validator(mode="after")
    def _params_match_checker(self) -> Assertion:
        try:
            CHECKERS[self.checker][0].model_validate(self.params)
        except ValidationError as e:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or '<params>'}: {err['msg']}"
                for err in e.errors()
            )
            raise ValueError(f"checker {self.checker}: invalid params: {problems}") from e
        return self

    @property
    def typed_params(self) -> BaseModel:
        return CHECKERS[self.checker][0].model_validate(self.params)


class Scope(_Strict):
    dataset: str | None = None
    column: str | None = None
    layer: str | None = None
    time: dict[str, str] | None = None


class Interpretation(_Strict):
    reliability: Literal["ok", "partial", "unreliable"] | None = None
    reason: str | None = None
    kind: str | None = None
    kind_label: str | None = None
    timezone: str | None = None
    label_column: str | None = None
    vintage: str | None = None
    #: What one row records, for a unit_of_observation claim (e.g. "dispatch").
    unit: str | None = None

    @field_validator("timezone")
    @classmethod
    def _valid_zone(cls, v: str | None) -> str | None:
        return _check_zone(v)


_PLACE_KINDS = frozenset(get_args(PlaceKind))


def _check_servable(kind: str, interp: Interpretation) -> None:
    """Reject at load a reviewed claim the engine would skip or fail on at describe."""
    if kind in ("place_field", "region_layer"):
        if interp.kind not in _PLACE_KINDS:
            raise ValueError(
                f"interpretation.kind must be one of {sorted(_PLACE_KINDS)} for a {kind} claim"
            )
        if interp.reliability is None:
            raise ValueError(f"interpretation.reliability is required for a {kind} claim")
    if kind == "region_layer" and interp.label_column is None:
        raise ValueError("interpretation.label_column is required for a region_layer claim")
    if kind == "column_timezone" and interp.timezone is None:
        raise ValueError("interpretation.timezone is required for a column_timezone claim")
    if kind == "unit_of_observation" and interp.unit is None:
        raise ValueError("interpretation.unit is required for a unit_of_observation claim")


class Claim(_Strict):
    id: str
    kind: Literal[
        "place_field",
        "region_layer",
        "placeholder_share",
        "column_timezone",
        "unit_of_observation",
        # Values carry leading or trailing whitespace, so an unpadded equality matches nothing.
        # Needs no interpretation.
        "padded_values",
    ]
    scope: Scope
    interpretation: Interpretation | None = None
    placeholders: list[str] | None = None
    reviewed_by: str | None = None
    reviewed_at: date | None = None
    evidence: list[Evidence]
    assertion: list[Assertion] = []

    @property
    def reviewed(self) -> bool:
        """True for a reviewer's interpretation or reviewed placeholder declaration.

        A claim with neither is a profiler observation.
        """
        if self.interpretation is not None:
            return True
        return (
            self.kind == "placeholder_share"
            and bool(self.placeholders)
            and self.reviewed_by is not None
            and self.reviewed_at is not None
        )

    @property
    def probes(self) -> list[SoqlProbe | MetadataProbe]:
        """The probe evidence in evidence order; an assertion's `probe` indexes this list."""
        return [e for e in self.evidence if isinstance(e, SoqlProbe | MetadataProbe)]

    @model_validator(mode="after")
    def _checks(self) -> Claim:
        if not self.evidence:
            raise ValueError("evidence must not be empty")
        if self.interpretation is not None and (
            self.reviewed_by is None or self.reviewed_at is None
        ):
            raise ValueError("an interpretation requires reviewed_by and reviewed_at")
        if self.interpretation is not None:
            _check_servable(self.kind, self.interpretation)
        if self.assertion and not any(
            isinstance(e, SoqlProbe | MetadataProbe) for e in self.evidence
        ):
            raise ValueError("assertions require a soql_probe or metadata_probe evidence")
        probes = self.probes
        for a in self.assertion:
            if a.probe >= len(probes):
                raise ValueError(
                    f"assertion {a.checker}: probe {a.probe} is out of range "
                    f"({len(probes)} probe evidence)"
                )
            want = CHECKERS[a.checker][1]
            if probes[a.probe].kind != want:
                raise ValueError(
                    f"assertion {a.checker} reads a {want}, but probe {a.probe} is a "
                    f"{probes[a.probe].kind}"
                )
        return self


class Pack(_Strict):
    claims: list[Claim] = []

    def place_fields(self, dataset_id: str) -> dict[str, Claim]:
        return {
            c.scope.column: c
            for c in self.claims
            if c.kind == "place_field" and c.scope.dataset == dataset_id and c.scope.column
        }

    def region_layer(self, layer_id: str) -> Claim | None:
        return next(
            (c for c in self.claims if c.kind == "region_layer" and c.scope.layer == layer_id),
            None,
        )

    def column_timezone(self, dataset_id: str, column: str) -> Claim | None:
        return next(
            (
                c
                for c in self.claims
                if c.kind == "column_timezone"
                and c.scope.dataset == dataset_id
                and c.scope.column == column
            ),
            None,
        )

    def placeholder_declarations(self, dataset_id: str, column: str) -> list[Claim]:
        """The column's reviewed placeholder declarations: its reviewed `placeholder_share`
        claims, and its reviewed `place_field` claims that carry `placeholders`."""
        return [
            c
            for c in self.claims
            if c.kind in ("placeholder_share", "place_field")
            and c.scope.dataset == dataset_id
            and c.scope.column == column
            and c.reviewed
            and c.placeholders
        ]

    def placeholders(self, dataset_id: str, column: str) -> frozenset[str]:
        """Every value the column's reviewed declarations make a placeholder, fresh or not."""
        return frozenset(
            v
            for c in self.placeholder_declarations(dataset_id, column)
            for v in c.placeholders or []
        )


@dataclass(frozen=True)
class PortalContext:
    identity: PortalIdentity
    pack: Pack
    guides: tuple[Guide, ...] = ()
    #: Claim id to its last drift check, for this portal (`validation.json`).
    checks: Mapping[str, ClaimCheck] = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.identity.id

    @property
    def tz(self) -> ZoneInfo | None:
        return ZoneInfo(self.identity.timezone) if self.identity.timezone else None

    @cached_property
    def guides_by_dataset(self) -> dict[str, Guide]:
        return {g.dataset_id: g for g in self.guides}

    @cached_property
    def guides_by_id(self) -> dict[str, Guide]:
        return {g.guide_id: g for g in self.guides}
