"""Pydantic models the data-access functions take and return (ADR-005)."""

from datetime import date

from pydantic import BaseModel, Field


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
