"""Pydantic models the data-access functions take and return (ADR-005)."""

from datetime import date
from typing import Any

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


class Hit(BaseModel):
    """One retrieval result: a distinct chunk text found for the question (S04-R2 decision 4).

    Many chunks can hold one text (one per version where a section didn't change). The hit cites
    the chunk in the newest version holding it, and lists the release window of every version
    holding it, so a gap between releases stays visible. Every other field is the cited chunk's
    or its version's, except the score and ranks, which say why it ranked where it did (S07-R1
    decision 4).
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
    claimed_status: str | None
    claimed_stage: str | None
    snapshot_repo: str
    snapshot_sha: str
    source_path: str
    metadata: dict[str, Any]  # the version's front matter, including `title`
    rrf_score: float | None = None  # the fused score, in hybrid and rerank modes only
    dense_rank: int | None = None  # position in the dense list, from 1; None if not in it
    lexical_rank: int | None = None  # position in the lexical list, from 1; None if not in it
    rerank_score: float | None = None  # the cross-encoder's raw score, in rerank mode only
