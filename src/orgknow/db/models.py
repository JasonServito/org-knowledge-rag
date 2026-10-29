"""Pydantic models the data-access functions take and return (ADR-005)."""

from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field


class Release(BaseModel):
    """One row of `releases`: a Kubernetes minor release and its support dates."""

    # "1.N" with no leading zeros, so it always equals the table's CHECK `'1.' || minor`.
    version: str = Field(pattern=r"^1\.(0|[1-9][0-9]*)$")
    release_date: date
    end_of_life_date: date

    @property
    def minor(self) -> int:
        """The table's key: 24 for "1.24"."""
        return int(self.version.removeprefix("1."))


class VersionData(BaseModel):
    """A version's columns except its document and id: what ingestion derives from snapshots.

    The table's CHECKs, not this model, validate hashes and windows (ADR-005 D2). The model
    only refuses naive datetimes, which the database would silently read in its own time zone.
    """

    content_hash: str
    source_path: str
    snapshot_repo: str
    snapshot_ref: str
    snapshot_sha: str
    valid_from_release: int
    valid_until_release: int | None = None
    valid_from_date: AwareDatetime
    valid_until_date: AwareDatetime | None = None
    claimed_status: str | None = None
    claimed_stage: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewVersion(VersionData):
    """A `document_versions` row to insert: every column except the generated `id`."""

    document_id: int


class Version(NewVersion):
    """A stored `document_versions` row, as the read functions return it."""

    id: int


class NewChunk(BaseModel):
    """A chunk to insert. No hash field: `add_chunks` computes `content_hash` from `text` (R13)."""

    ordinal: int
    heading_path: list[str]
    text: str


class VersionToChunk(BaseModel):
    """A stored version with no chunks yet: where to re-read its file, and its header fields."""

    id: int
    canonical_id: str
    source_type: str
    source_path: str
    snapshot_repo: str
    snapshot_sha: str
    metadata: dict[str, Any]


class TextToEmbed(BaseModel):
    """A chunk text with no vector yet for a model. Many chunks can share it (same hash)."""

    content_hash: str
    text: str


class Counts(BaseModel):
    """The ingestion report's counts for one group of stored rows (S05-T8). `release` and
    `source_type` say which group; None means all (a total)."""

    release: int | None = None
    source_type: str | None = None
    documents: int
    versions: int
    chunks: int
    texts: int  # distinct chunk texts (content hashes): one vector each


# The fingerprint's view of each stored record (S05-R3 decision 8): every stored value except
# generated ids. A record names its document by canonical_id, and a chunk names its version by
# the version's valid_from_date, unique per document (R8).


class StoredDocument(BaseModel):
    canonical_id: str
    source_type: str


class StoredAlias(BaseModel):
    canonical_id: str  # the document it points to
    alias: str


class StoredVersion(VersionData):
    canonical_id: str


class StoredChunk(BaseModel):
    canonical_id: str
    valid_from_date: AwareDatetime  # its version's
    ordinal: int
    heading_path: list[str]
    content_hash: str


class SectionText(BaseModel):
    """One distinct chunk text of a document and its heading path (S06-T1): what a golden-set
    label is checked against."""

    heading_path: list[str]
    content_hash: str


Confidence = Literal["high", "low"]  # ADR-003 D5's status_confidence


class Observation(BaseModel):
    """One `observed_lifecycle` row: a feature gate's stage at a minor release, as that release's
    own feature-gate reference gives it (ADR-003 D2). The table's CHECKs, not this model, check
    that a high row has a stage from the vocabulary."""

    gate: str  # the name the release's reference gives it
    release: int  # the minor: 24 for v1.24
    stage: str | None  # None: no stage could be read (always low)
    status_confidence: Confidence


class Authority(BaseModel):
    """A hit's authority at the question's target release (S09-T6; ADR-003 D2-D3 as changed in
    the S09-R2 design review): its tier, and for a KEP its effective stage there."""

    target_release: int  # the minor the question asks about: 37 for 1.37
    # 1 (docs pages, the feature-gate reference) to 6 (blog posts); None: a superseded proposal
    # (a KEP claiming withdrawn, rejected or replaced).
    tier: int | None
    # KEPs only: the stage its gates' rows give at the target release (high), else its claimed
    # stage (low); None (confidence None) with neither.
    effective_stage: str | None
    stage_confidence: Confidence | None


class NewestVersion(BaseModel):
    """A document's newest version (latest date window), as much as its tier reads (S09-T6): for
    the golden labels' tiers (S09-T7). Also its newest version valid at a release, for a KEP's
    claim and its gates (S10-T2: `kep_versions_at`)."""

    canonical_id: str
    source_type: str
    claimed_status: str | None
    claimed_stage: str | None
    metadata: dict[str, Any]  # a KEP's holds its `kep.yaml`, `feature-gates` included


class Hit(BaseModel):
    """One retrieval result: a distinct chunk text found for the question (S04-R2 decision 4).

    Many chunks can hold one text (one per version where a section didn't change). The hit cites
    the chunk in the newest version holding it, and lists the release window of every version
    holding it, so a gap between releases stays visible. `current` also reads every version
    holding it (S09-T3). Every other field is the cited chunk's or its version's, except the
    score and ranks, which say why it ranked where it did (S07-R1 decision 4).
    """

    chunk_id: int  # what a citation points to
    content_hash: str
    # Cosine distance to the question, 0 (same direction) to 2 (opposite). None when only
    # lexical search found the text: no vector was compared.
    distance: float | None
    text: str  # header + body, exactly as embedded
    canonical_id: str
    source_type: str
    heading_path: list[str]
    # (valid_from_release, valid_until_release) per version, by from-release; None is open.
    release_windows: list[tuple[int, int | None]]
    # Whether some version holding the text is current (an open date window): False when later
    # edits replaced the text everywhere, i.e. a stale hit (S09-R1 decision 1).
    current: bool
    claimed_status: str | None
    claimed_stage: str | None
    snapshot_repo: str
    snapshot_sha: str
    source_path: str
    metadata: dict[str, Any]  # the version's front matter, including `title`
    rrf_score: float | None = None  # the fused score, in hybrid, rerank and temporal modes only
    dense_rank: int | None = None  # position in the dense list, from 1; None if not in it
    lexical_rank: int | None = None  # position in the lexical list, from 1; None if not in it
    rerank_score: float | None = None  # the cross-encoder's raw score (rerank and temporal modes)
    # The tier and a KEP's stage at the question's target release, set by `retrieve` in every
    # mode (S09-T6); None on the search functions' own hits.
    authority: Authority | None = None
    # Authority mode only (S09-T7): the reranker's probability, sigmoid(rerank_score), times the
    # hit's authority factor, unrounded; the hits are ordered by it rounded to 4 decimals.
    authority_score: float | None = None


class TemporalFilter(BaseModel):
    """Which texts both searches keep for one question (S09-R1 decisions 2-4): a text is kept when
    some version holding it passes. `current_only`: the version is still current (no
    `valid_until_date`). `from_release` / `until_release`: the version's release window overlaps
    them, inclusive; None is an open end."""

    current_only: bool
    from_release: int | None
    until_release: int | None


# The decision chain (S13-T3; ADR-012 D1-D2; the S13-R1 plan's "Pinned: T3"): migration
# 0008's CHECK lists, as types.
Step = Literal["problem", "discussion", "proposal", "decision", "implementation", "current_docs"]
FoundBy = Literal["seed", "template_field", "merge_event", "linking_text", "similarity"]
MissingReason = Literal[
    "no_tracking_issue", "no_link", "not_public", "not_ingested", "not_merged", "no_linking_text"
]


class DocumentChunk(BaseModel):
    """One chunk of a document's newest version, as the chain rules read it."""

    id: int
    ordinal: int
    heading_path: list[str]
    text: str  # header + body, as stored
    content_hash: str


class ChainDocument(BaseModel):
    """A document's newest version (latest date window) and its chunks, by ordinal: a seed KEP
    or a GitHub item, as the chain rules read it."""

    document_id: int
    canonical_id: str
    source_type: str
    source_path: str
    metadata: dict[str, Any]  # a KEP's `kep.yaml`; a GitHub item's dates and url
    chunks: list[DocumentChunk]


class LinkCandidate(BaseModel):
    """A blog post or release record chunk whose text holds a KEP's number: a candidate for the
    implementation step (rule 7), one per chunk of every version."""

    chunk_id: int
    canonical_id: str
    source_type: str
    ordinal: int
    heading_path: list[str]
    text: str
    valid_from_date: AwareDatetime  # its version's date-window start


class NearText(BaseModel):
    """A text near a KEP's Summary vector, among those valid at the latest release (rule 8),
    with the chunk that cites it: in the newest such version holding it."""

    content_hash: str
    distance: float  # cosine distance, 0 (same direction) to 2
    chunk_id: int
    canonical_id: str
    heading_path: list[str]
    valid_from_date: AwareDatetime  # the cited chunk's version's date-window start


class NewEvidence(BaseModel):
    """A `decision_evidence` row to insert: a step that cites a chunk (with how it was found),
    or a step that is missing (with its reason). The table's CHECKs, not this model, enforce
    "exactly one of the two"."""

    step: Step
    chunk_id: int | None = None
    occurred_at: AwareDatetime | None = None
    found_by: FoundBy | None = None
    via_chunk_id: int | None = None  # the chunk holding the link that connects this step
    missing_reason: MissingReason | None = None


class StoredEvidence(BaseModel):
    """A stored step, with what a citation shows: the cited chunk's document, heading path and
    version fields, and the via chunk's document and heading path. A missing step has only its
    step and reason."""

    step: Step
    occurred_at: AwareDatetime | None
    found_by: FoundBy | None
    missing_reason: MissingReason | None
    chunk_id: int | None
    canonical_id: str | None
    source_type: str | None
    heading_path: list[str] | None
    claimed_status: str | None
    snapshot_repo: str | None
    snapshot_sha: str | None
    source_path: str | None
    metadata: dict[str, Any] | None
    via_chunk_id: int | None
    via_canonical_id: str | None
    via_heading_path: list[str] | None


class StoredDecision(BaseModel):
    """A stored decision chain: its seed KEP, title, build time and steps, in step order."""

    seed: str  # the seed KEP's canonical id
    title: str
    built_at: AwareDatetime
    steps: list[StoredEvidence]


# Ingestion jobs (S14-T4; ADR-013 D6; the S14-R2 plan's "Pinned: T4"): migration 0009's
# CHECK list, and the statuses a step in a job's `steps` list can have.
JobStatus = Literal["queued", "running", "succeeded", "failed"]
StepStatus = Literal["pending", "running", "succeeded", "failed"]


class JobStep(BaseModel):
    """One step of an ingestion job, as its row's `steps` list stores it."""

    name: str  # ingest, lifecycle, embed or chains (`db/jobs.py`)
    status: StepStatus = "pending"
    started_at: AwareDatetime | None = None
    finished_at: AwareDatetime | None = None
    # What the step reports (S14-R2 call d), e.g. ingest's new versions and its fingerprint.
    counts: dict[str, int | str] = Field(default_factory=dict)
    error: str | None = None  # a failed step's one-line reason


class IngestionJob(BaseModel):
    """One `ingestion_jobs` row, its steps in order. The API returns it as is."""

    id: int
    status: JobStatus
    created_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    attempts: int  # runs and resumes started (ADR-013 D5)
    error: str | None  # a failed job's one-line reason
    request_id: str | None  # the X-Request-ID of the POST that created it
    steps: list[JobStep]
