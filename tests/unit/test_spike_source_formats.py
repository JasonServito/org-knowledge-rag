"""Tests for the S02-T5b spike, spikes/source_formats.py.

Replace in S04/S05: CHANGELOG sectioning and KEP metadata parsing are rewritten in src/ with
their own tests. Delete this file then, together with the spike.
"""

import importlib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import yaml

SPIKES = Path(__file__).resolve().parents[2] / "spikes"

# CHANGELOG layout: a generated TOC, then one level-1 section per release, newest first.
CHANGELOG = """\
<!-- BEGIN MUNGE: GENERATED_TOC -->
- [v1.28.1](#v1281)
<!-- END MUNGE: GENERATED_TOC -->

# v1.28.1

## Downloads for v1.28.1

```shell
# not a heading: a comment in a code block
```

## Changelog since v1.28.0

# v1.28.0

## Changes by Kind
"""
V1_28_2 = "# v1.28.2\n\n## Changelog since v1.28.1\n\n"


@pytest.fixture(scope="module")
def sf() -> Iterator[ModuleType]:
    with pytest.MonkeyPatch.context() as mp:
        mp.syspath_prepend(str(SPIKES))  # source_formats.py imports its sibling spikes
        yield importlib.import_module("source_formats")


def test_changelog_sections_split_at_level_one_outside_fences(sf: ModuleType) -> None:
    preamble, sections = sf.changelog_sections(CHANGELOG)
    assert "GENERATED_TOC" in preamble
    assert [heading for heading, _ in sections] == ["v1.28.1", "v1.28.0"]
    assert "# not a heading" in sections[0][1]  # the fence stays inside its section
    assert sections[1][1] == "# v1.28.0\n\n## Changes by Kind\n"  # the text is kept as is


def test_changelog_sections_survive_a_stray_fence_in_a_list_item(sf: ModuleType) -> None:
    # CHANGELOG-1.22 line 3085: a release note ends with the PR template's closing fence, with
    # no opening one. A fence in a list item ends with the item, so the next heading still splits.
    stray = "# v1.28.1\n\n- A note.\n  ```\n\n  #### Additional documentation\n\n" + V1_28_2
    assert [h for h, _ in sf.changelog_sections(stray)[1]] == ["v1.28.1", "v1.28.2"]


def test_duplicate_headings(sf: ModuleType) -> None:
    _, sections = sf.changelog_sections(CHANGELOG + "# v1.28.0\n")
    assert sf.duplicate_headings(sections) == ["v1.28.0"]
    assert sf.duplicate_headings(sf.changelog_sections(CHANGELOG)[1]) == []


def test_compare_pairs_by_heading_not_position(sf: ModuleType) -> None:
    old = sf.changelog_sections(CHANGELOG)[1]
    new = sf.changelog_sections(V1_28_2 + CHANGELOG)[1]  # a new release is prepended
    assert sf.compare_sections(old, new) == {
        "identical": ["v1.28.1", "v1.28.0"],
        "added": ["v1.28.2"],
    }


def test_compare_reports_duplicates_without_pairing_them(sf: ModuleType) -> None:
    old = sf.changelog_sections(CHANGELOG)[1]
    new = sf.changelog_sections(CHANGELOG + "# v1.28.0\n")[1]
    assert sf.compare_sections(old, new) == {
        "identical": ["v1.28.1"],
        "duplicate heading": ["v1.28.0"],
    }


def test_compare_verdicts(sf: ModuleType) -> None:
    old = sf.changelog_sections(CHANGELOG)[1]
    spacing = CHANGELOG.replace("\n", "\r\n").replace("## Changes by Kind", "## Changes by Kind  ")
    assert sf.compare_sections(old, sf.changelog_sections(spacing)[1]) == {
        "identical after clean_text": ["v1.28.1", "v1.28.0"],  # CRLF and trailing spaces only
    }
    truncated = CHANGELOG.split("# v1.28.0")[0]
    assert sf.compare_sections(old, sf.changelog_sections(truncated)[1]) == {
        "identical": ["v1.28.1"],
        "removed": ["v1.28.0"],  # dropped from the new file
    }
    edited = CHANGELOG.replace("Changes by Kind", "Changes by kind")
    assert sf.compare_sections(old, sf.changelog_sections(edited)[1])["changed"] == ["v1.28.0"]


def test_first_changed_line(sf: ModuleType) -> None:
    assert sf.first_changed_line("a\nb\nc", "a\nB\nc") == ("b", "B")
    assert sf.first_changed_line("a\nb", "a") == ("b", "")


def test_heading_kind(sf: ModuleType) -> None:
    assert sf.heading_kind("Downloads for v1.28.15") == "Downloads for <v>"
    assert sf.heading_kind("Changelog since v1.28.0-rc.1") == "Changelog since <v>"
    assert sf.heading_kind("Changes by Kind") == "Changes by Kind"


def test_classify(sf: ModuleType) -> None:
    template, lifecycle = sf.TEMPLATE_STAGES, sf.LIFECYCLE_STAGES
    assert sf.classify("stable", template) == "in vocabulary"
    assert sf.classify(" Stable", template) == "normalizes"  # case and whitespace only
    assert sf.classify("GA", template) == "out of vocabulary"  # reported, not mapped
    assert sf.classify("deprecated", template) == "out of vocabulary"
    assert sf.classify("deprecated", lifecycle) == "in vocabulary"
    assert sf.classify("disabled", lifecycle) == "out of vocabulary"
    assert sf.classify(None, template) == "missing"
    assert sf.classify(1.3, template) == "not a string"


def test_non_string_milestones(sf: ModuleType) -> None:
    meta = yaml.safe_load('latest-milestone: 1.30\nmilestone: {alpha: yes, beta: "v1.21"}\n')
    assert meta["latest-milestone"] == 1.3  # the YAML trap: an unquoted 1.30 is the float 1.3
    assert sf.non_string_milestones(meta) == [("latest-milestone", 1.3), ("milestone.alpha", True)]
    quoted = yaml.safe_load('latest-milestone: "1.30"\nmilestone: {alpha: v1.20, beta: on}\n')
    assert sf.non_string_milestones(quoted) == [("milestone.beta", True)]  # YAML 1.1: on = true
    assert sf.non_string_milestones({"latest-milestone": None, "milestone": None}) == []


def test_raw_field(sf: ModuleType) -> None:
    text = 'title: x\nlatest-milestone: "v1.27"\nmilestone:\n  date: 2020-01-01\nDate: 2024-05-20\n'
    assert sf.raw_field(text, "latest-milestone") == '"v1.27"'  # as written, quotes included
    assert sf.raw_field(text, "date") == "2024-05-20"  # top level only; keys ignore case
    assert sf.raw_field(text, "stage") is None


def test_date_shape(sf: ModuleType) -> None:
    assert sf.date_shape("2024-05-20") == "9999-99-99"
    assert sf.date_shape('"2025-11-11T10:30:00-08:00"') == '"9999-99-99T99:99:99-99:99"'
    assert sf.date_shape(None) == "missing"
