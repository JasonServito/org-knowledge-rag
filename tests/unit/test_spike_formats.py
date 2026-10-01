"""Tests for the S02-T5 spike, spikes/formats.py.

Replace in S04/S05: feature-gate parsing is rewritten in src/ with its own tests.
Delete this file then, together with the spike.
"""

import importlib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import yaml

SPIKES = Path(__file__).resolve().parents[2] / "spikes"

# The pre-1.29 layout: a header, a separator, then one row per gate and stage.
# An open Until is either empty or `-`.
TABLE = """\
| Feature | Default | Stage | Since | Until |
|---------|---------|-------|-------|-------|
| `APIListChunking` | `false` | Alpha | 1.8 | 1.8 |
| `APIListChunking` | `true` | Beta | 1.9 | |
| `PodSecurity` | `false` | Alpha | 1.22 | 1.22 |
| `PodSecurity` | `true` | Beta | 1.23 | 1.24 |
| `PodSecurity` | `true` | GA | 1.25 | - |
"""
# feature-gates-removed.md (1.25-1.28) names its columns From and To.
REMOVED = """\
| Feature | Default | Stage | From | To |
|---------|---------|-------|------|----|
| `Accelerators` | `false` | Alpha | 1.6 | 1.10 |
| `Accelerators` | - | Deprecated | 1.11 | 1.11 |
"""
GATE_FILE = """\
title: LegacyServiceAccountTokenCleanUp
stages:
  - stage: alpha
    defaultValue: false
    fromVersion: "1.28"
    toVersion: "1.28"
  - stage: beta
    defaultValue: true
    fromVersion: "1.29"
    toVersion: "1.29"
  - stage: stable
    defaultValue: true
    locked: true
    fromVersion: "1.30"
"""


@pytest.fixture(scope="module")
def formats() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(SPIKES))  # formats.py imports its siblings fetch.py and measure.py
        yield importlib.import_module("formats")


def test_version_key_is_numeric(formats: ModuleType) -> None:
    key = formats.version_key
    assert key("1.9") < key("1.10") < key("1.28")
    assert key("1.37") == key("v1.37.0")
    assert [key(text) for text in ("", "GA", "1", "1.x")] == [None] * 4


def test_version_key_orders_pre_releases(formats: ModuleType) -> None:
    key = formats.version_key
    order = ["v1.36.4", "v1.37.0-alpha.1", "v1.37.0-alpha.2", "v1.37.0-beta.0", "v1.37.0-rc.1"]
    order += ["v1.37.0", "v1.37.1"]
    assert sorted(order, key=key) == order


def test_gate_table_rows_groups_rows_per_gate(formats: ModuleType) -> None:
    assert formats.gate_table_rows(TABLE) == {
        "APIListChunking": [("Alpha", "1.8", "1.8"), ("Beta", "1.9", None)],
        "PodSecurity": [("Alpha", "1.22", "1.22"), ("Beta", "1.23", "1.24"), ("GA", "1.25", None)],
    }


def test_gate_table_rows_reads_the_removed_gates_table(formats: ModuleType) -> None:
    assert formats.gate_table_rows(REMOVED) == {
        "Accelerators": [("Alpha", "1.6", "1.10"), ("Deprecated", "1.11", "1.11")],
    }


def test_gate_stages_ignores_extra_keys(formats: ModuleType) -> None:
    assert formats.gate_stages(yaml.safe_load(GATE_FILE)) == [
        ("alpha", "1.28", "1.28"),
        ("beta", "1.29", "1.29"),
        ("stable", "1.30", None),  # open-ended: no toVersion
    ]
    assert formats.gate_stages({"title": "NoStages"}) == []


def test_gate_ranges(formats: ModuleType) -> None:
    texts = {"t": TABLE, "r": REMOVED, "g": f"---\n{GATE_FILE}---\n", "i": "---\ntitle: x\n---\n"}
    tables = formats.gate_ranges(
        {"g/feature-gates.md": "t", "g/feature-gates-removed.md": "r"}, texts
    )
    assert sorted(tables) == ["APIListChunking", "Accelerators", "PodSecurity"]  # both pages
    files = formats.gate_ranges({"g/index.md": "i", "g/legacy-token.md": "g"}, texts)
    assert list(files) == ["LegacyServiceAccountTokenCleanUp"]  # by title; index.md skipped


def test_norm_stage(formats: ModuleType) -> None:
    assert formats.norm_stage(" Alpha ") == "alpha"
    assert formats.norm_stage("GA") == "stable"  # the tables say GA, the files say stable
    assert formats.norm_stage("Disabled") == "disabled"  # reported as is, not mapped


def test_stage_at(formats: ModuleType) -> None:
    ranges = formats.gate_table_rows(TABLE)["PodSecurity"]
    assert formats.stage_at(ranges, "1.21") is None  # before the first range
    assert formats.stage_at(ranges, "1.22") == "Alpha"
    assert formats.stage_at(ranges, "1.24") == "Beta"  # Until is inclusive
    assert formats.stage_at(ranges, "1.37") == "GA"  # the open-ended last stage runs on
    removed = formats.gate_table_rows(REMOVED)["Accelerators"]
    assert formats.stage_at(removed, "1.12") is None  # after the last closed range


def test_range_problems(formats: ModuleType) -> None:
    problems = formats.range_problems
    assert problems(formats.gate_table_rows(TABLE)["PodSecurity"]) == []
    assert problems(formats.gate_stages(yaml.safe_load(GATE_FILE))) == []
    assert problems([("alpha", "1.8", "1.9"), ("beta", "1.11", None)]) == ["gap"]
    assert problems([("alpha", "1.8", "1.10"), ("beta", "1.10", None)]) == ["overlap"]
    # A stage can change at a patch release: 1.35.3 -> 1.35.4 is contiguous.
    assert problems([("beta", "1.35.0", "1.35.3"), ("beta", "1.35.4", "1.36")]) == []
    assert problems([("beta", "1.31.0", "1.31.0"), ("deprecated", "1.31.1", None)]) == []
    assert problems([("alpha", "1.8", None), ("beta", "1.10", None)]) == ["open range not last"]
    assert problems([("beta", "1.12", "1.10")]) == ["ends before it starts"]
    assert problems([("alpha", "", "1.10")]) == ["unparseable version"]


def test_first_difference(formats: ModuleType) -> None:
    table = formats.gate_table_rows(TABLE)["PodSecurity"]
    files = [("alpha", "1.22", "1.22"), ("beta", "1.23", "1.24"), ("stable", "1.25", "1.27")]
    versions = [f"1.{minor}" for minor in range(29)]
    assert formats.norm_at(table, "1.25") == "stable"  # GA in the table
    assert formats.first_difference(table, files, versions) == "1.28"  # the files close at 1.27
    assert formats.first_difference(table[:2], files[:2], versions) is None
