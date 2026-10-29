"""S09-T5: a feature gate's stage at a release, from that release's own feature-gate reference
(ADR-003 D2; the S09-R2 plan's T5 rules).

Fixtures are real corpus files, copied byte-exact (CC BY 4.0):
- website_s09/feature-gates-tables/main-excerpt-1.25.md: feature-gates.md lines 214-232, the
  start of the graduated or deprecated table: `Since | Until`, with `-` and empty Until cells
  (website 8eb33afd, release-1.25).
- website_s09/feature-gates-tables/removed-excerpt-1.25.md: feature-gates-removed.md lines 31-36,
  the start of its table: `From | To`, with `-` in the Default column (website 8eb33afd).
- website_s05/feature-gates/<gate>/1.N.md: the gate's file at release 1.N (S05-T3).

Every expected value was worked out by hand from the plan's rules, or read from the fixtures
by hand; none is computed by the code under test.
"""

from pathlib import Path

import pytest
import yaml

from orgknow.db.models import Observation
from orgknow.ingestion.lifecycle import (
    Range,
    file_ranges,
    lifecycle_line,
    minor,
    stage_at,
    table_ranges,
)
from orgknow.ingestion.normalize import decode, split_front_matter

FIXTURES = Path(__file__).parents[1] / "fixtures"
TABLES = FIXTURES / "website_s09" / "feature-gates-tables"
GATES = FIXTURES / "website_s05" / "feature-gates"
SYNONYMS = {"GA": "stable"}  # settings.claim_synonyms' default, the one ADR-003 D5 allows


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("1.24", 24),
        ("v1.22", 22),
        ("1.31.0", 31),
        ("v1.37.0-alpha.1", 37),
        ("1.22.0-rc.2", 22),
        ("1,24", None),  # SetHostnameAsFQDN's typo
        ("2.1", None),  # not a 1.N version
        ("1.24.x", None),
        ("", None),
        (1.3, None),  # what YAML gives for an unquoted 1.30
    ],
)
def test_minor(version: object, expected: int | None) -> None:
    assert minor(version) == expected


def test_one_stage_per_release_from_closed_ranges() -> None:
    # PodSecurity's shape: alpha 1.22-1.22, beta 1.23-1.24, GA 1.25-1.27.
    ranges = [
        Range("Alpha", "1.22", "1.22"),
        Range("Beta", "1.23", "1.24"),
        Range("GA", "1.25", "1.27"),
    ]
    assert stage_at(ranges, 22, SYNONYMS) == ("alpha", "high")
    assert stage_at(ranges, 25, SYNONYMS) == ("stable", "high")  # GA is stable
    assert stage_at(ranges, 28, SYNONYMS) is None  # no range covers 28: no row


def test_two_stages_covering_a_release_give_no_stage() -> None:
    # CSIMigrationAWS on the 1.20 page: alpha 1.14- and beta 1.17-, both open, both cover 20.
    ranges = [Range("Alpha", "1.14", None), Range("Beta", "1.17", None)]
    assert stage_at(ranges, 20, SYNONYMS) == (None, "low")


def test_a_stage_outside_the_vocabulary_is_kept_as_written() -> None:
    # LegacyNodeRoleBehavior on the 1.20 page: `True` 1.19-.
    assert stage_at([Range("True", "1.19", None)], 20, SYNONYMS) == ("True", "low")


def test_an_unparseable_bound_gives_no_stage() -> None:
    # SetHostnameAsFQDN from the 1.25 page on: GA 1.22-`1,24`. Read as 1.24, it wouldn't cover
    # 25; unparseable, the release's stage can't be read at all.
    assert stage_at([Range("GA", "1.22", "1,24")], 25, SYNONYMS) == (None, "low")


def test_a_stage_change_at_a_patch_gives_no_stage() -> None:
    ranges = [Range("beta", "1.31.0", "1.31.0"), Range("deprecated", "1.31.1", None)]
    assert stage_at(ranges, 31, SYNONYMS) == (None, "low")


def test_one_stage_over_a_patch_boundary_is_high() -> None:
    ranges = [Range("beta", "1.35.0", "1.35.3"), Range("beta", "1.35.4", "1.36")]
    assert stage_at(ranges, 35, SYNONYMS) == ("beta", "high")


def test_a_yaml_number_is_not_a_version() -> None:
    metadata = yaml.safe_load("stages:\n  - stage: beta\n    fromVersion: 1.30\n")
    assert metadata["stages"][0]["fromVersion"] == 1.3  # YAML read an unquoted number
    assert stage_at(file_ranges(metadata), 30, SYNONYMS) == (None, "low")


def test_table_rows_of_a_since_until_page() -> None:
    # The header and separator rows have no `Name` cell: no row. `-` and an empty cell are open.
    text = decode((TABLES / "main-excerpt-1.25.md").read_bytes())
    assert table_ranges(text) == {
        "AdvancedAuditing": [
            Range("Alpha", "1.7", "1.7"),
            Range("Beta", "1.8", "1.11"),
            Range("GA", "1.12", None),
        ],
        "CSIInlineVolume": [
            Range("Alpha", "1.15", "1.15"),
            Range("Beta", "1.16", "1.24"),
            Range("GA", "1.25", None),
        ],
        "CSIMigration": [
            Range("Alpha", "1.14", "1.16"),
            Range("Beta", "1.17", "1.24"),
            Range("GA", "1.25", None),
        ],
        "CSIMigrationAWS": [
            Range("Alpha", "1.14", "1.16"),
            Range("Beta", "1.17", "1.22"),
            Range("Beta", "1.23", "1.24"),
            Range("GA", "1.25", None),
        ],
        "CSIMigrationAzureDisk": [
            Range("Alpha", "1.15", "1.18"),
            Range("Beta", "1.19", "1.22"),
            Range("Beta", "1.23", "1.23"),
            Range("GA", "1.24", None),
        ],
    }


def test_table_rows_of_a_from_to_page() -> None:
    # A `-` in the Default column is just a default: the row still counts.
    text = decode((TABLES / "removed-excerpt-1.25.md").read_bytes())
    assert table_ranges(text) == {
        "Accelerators": [Range("Alpha", "1.6", "1.10"), Range("Deprecated", "1.11", "1.11")],
        "AffinityInAnnotations": [Range("Alpha", "1.6", "1.7"), Range("Deprecated", "1.8", "1.8")],
    }


def test_stage_at_from_a_table_page() -> None:
    gates = table_ranges(decode((TABLES / "main-excerpt-1.25.md").read_bytes()))
    # CSIMigrationAWS: beta 1.23-1.24 covers 23 (beta 1.17-1.22 doesn't); GA 1.25- covers 25.
    assert stage_at(gates["CSIMigrationAWS"], 23, SYNONYMS) == ("beta", "high")
    assert stage_at(gates["CSIMigrationAWS"], 25, SYNONYMS) == ("stable", "high")


def test_file_ranges_of_a_gate_file() -> None:
    front_matter, _ = split_front_matter(
        decode((GATES / "StrictIPCIDRValidation" / "1.37.md").read_bytes())
    )
    ranges = file_ranges(front_matter)
    assert ranges == [Range("alpha", "1.33", "1.35"), Range("beta", "1.36", None)]
    assert stage_at(ranges, 37, SYNONYMS) == ("beta", "high")
    assert stage_at(ranges, 34, SYNONYMS) == ("alpha", "high")
    assert stage_at(ranges, 32, SYNONYMS) is None


def test_a_stage_is_stripped_before_it_is_read() -> None:
    # The file writes `stage: alpha ` (a trailing space): still alpha, high.
    front_matter, _ = split_front_matter(
        decode((GATES / "APIServingWithRoutine" / "1.33.md").read_bytes())
    )
    assert stage_at(file_ranges(front_matter), 33, SYNONYMS) == ("alpha", "high")


def test_lifecycle_line() -> None:
    rows = [
        Observation(gate="A", release=20, stage="alpha", status_confidence="high"),
        Observation(gate="A", release=21, stage=None, status_confidence="low"),
        Observation(gate="B", release=21, stage="True", status_confidence="low"),
    ]
    assert lifecycle_line(rows) == "Observed lifecycle: 3 rows over 2 releases (1 high, 2 low)."
