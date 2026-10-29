from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from orgknow.db.models import NewVersion


def _fields(**changes: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "document_id": 1,
        "content_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "source_path": "content/en/docs/concepts/security/pod-security-policy.md",
        "snapshot_repo": "website",
        "snapshot_ref": "release-1.24",
        "snapshot_sha": "0123456789abcdef0123456789abcdef01234567",
        "valid_from_release": 24,
        "valid_until_release": 24,
        "valid_from_date": datetime(2022, 5, 3, tzinfo=UTC),
        "valid_until_date": datetime(2022, 8, 23, tzinfo=UTC),
    }
    return fields | changes


def test_accepts_timezone_aware_datetimes() -> None:
    # The control for the test below: without its one change, the model builds.
    version = NewVersion(**_fields())

    assert version.valid_from_date == datetime(2022, 5, 3, tzinfo=UTC)
    assert version.metadata == {}


@pytest.mark.parametrize("field", ["valid_from_date", "valid_until_date"])
def test_rejects_a_naive_datetime(field: str) -> None:
    with pytest.raises(ValidationError, match="timezone"):
        NewVersion(**_fields(**{field: datetime(2022, 5, 3)}))
