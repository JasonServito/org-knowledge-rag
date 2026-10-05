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


class NewVersion(BaseModel):
    """A `document_versions` row to insert: every column except the generated `id`.

    The table's CHECKs, not this model, validate hashes and windows (ADR-005 D2). The model
    only refuses naive datetimes, which the database would silently read in its own time zone.
    """

    document_id: int
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


class Version(NewVersion):
    """A stored `document_versions` row, as the read functions return it."""

    id: int


class NewChunk(BaseModel):
    """A chunk to insert. No hash field: `add_chunks` computes `content_hash` from `text` (R13)."""

    ordinal: int
    heading_path: list[str]
    text: str
