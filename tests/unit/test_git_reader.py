"""Reading snapshots from git: which files are read, skipped, and when commits happened.

Every repo here is a tiny local one built by the test (no network).
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from orgknow.ingestion.git_reader import (
    GitError,
    merge_time,
    parse_commit_time,
    read_files,
    similar_renames,
)
from orgknow.ingestion.manifest import Snapshot

PAGE = b"---\ntitle: Page\n---\nBody\n"


def test_reads_markdown_and_skips_symlinks_and_other_files_with_a_reason(
    make_git_repo: Callable[[str], Any],
) -> None:
    repo = make_git_repo("website")
    docs = repo.path / "docs"
    first = repo.commit({"docs/a.md": PAGE, "docs/diagram.svg": b"<svg/>"})
    os.symlink("a.md", docs / "link.md")
    second = repo.commit({"docs/a.md": None, "docs/b.md": PAGE})
    snapshots = [Snapshot(24, "release-1.24", first), Snapshot(25, "release-1.25", second)]

    files, skipped = read_files(repo.path, ["docs/"], snapshots, (".md",))

    # a.md is gone at 1.25 (None); b.md is new there.
    assert files == {"docs/a.md": [PAGE, None], "docs/b.md": [None, PAGE]}
    assert skipped == [
        "1.24 docs/diagram.svg: not a .md file",
        "1.25 docs/diagram.svg: not a .md file",
        "1.25 docs/link.md: symlink",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # Real committer times of KEP-2579 commits 313ad8b5, 9f14627a and 69d3fac5.
        ("2022-09-22T10:28:05+02:00", datetime(2022, 9, 22, 8, 28, 5, tzinfo=UTC)),
        ("2022-08-31T15:51:14-04:00", datetime(2022, 8, 31, 19, 51, 14, tzinfo=UTC)),
        ("2021-11-04T21:29:13-04:00", datetime(2021, 11, 5, 1, 29, 13, tzinfo=UTC)),
    ],
)
def test_commit_times_are_converted_to_utc(text: str, expected: datetime) -> None:
    parsed = parse_commit_time(text)

    assert parsed == expected
    assert parsed.utcoffset() is not None
    assert parsed.tzinfo == UTC


def test_a_commit_time_without_an_offset_is_refused() -> None:
    with pytest.raises(ValueError, match="no UTC offset"):
        parse_commit_time("2022-09-22T10:28:05")


PATHS = ["kep/README.md", "kep/kep.yaml"]


def test_merge_time_is_the_last_commit_touching_the_files_since_the_previous_snapshot(
    make_git_repo: Callable[[str], Any],
) -> None:
    repo = make_git_repo("enhancements")
    previous = repo.commit({"kep/README.md": b"v1"}, when="2022-06-01T17:05:45-07:00")
    repo.commit({"kep/README.md": b"v2"}, when="2022-08-31T15:51:14-04:00")
    touched = repo.commit({"kep/kep.yaml": b"stage: beta\n"}, when="2022-09-22T10:28:05+02:00")
    current = repo.commit({"other/file.md": b"x"}, when="2022-10-01T00:00:00+00:00")

    # The last of the two commits touching the files, not the later one touching other/.
    last = datetime(2022, 9, 22, 8, 28, 5, tzinfo=UTC)
    assert merge_time(repo.path, previous, current, PATHS) == last
    assert merge_time(repo.path, None, current, PATHS) == last  # the whole history
    assert merge_time(repo.path, touched, current, PATHS) is None  # nothing touched them since


def test_merge_time_is_when_the_change_was_merged_not_when_it_was_committed(
    make_git_repo: Callable[[str], Any],
) -> None:
    # KEP-2579's first version (S05-R2 contract): its branch's last commit is 182464a6
    # (2021-05-11T20:46:27Z); master merged it on 2021-05-12T16:25:28Z (7712007e).
    repo = make_git_repo("enhancements")
    previous = repo.commit({"README.md": b"# Enhancements\n"}, when="2021-04-01T00:00:00+00:00")
    repo.switch("kep-2579", create=True)
    repo.commit(
        {"kep/README.md": b"v1", "kep/kep.yaml": b"stage: alpha\n"},
        when="2021-05-11T13:42:01-07:00",
    )
    repo.commit({"kep/README.md": b"v1, fixed typo"}, when="2021-05-11T13:46:27-07:00")
    repo.switch("main")
    repo.commit({"other/file.md": b"x"}, when="2021-05-12T09:00:00+00:00")  # main moved on
    repo.merge("kep-2579", when="2021-05-12T16:25:28+00:00")
    current = repo.commit({"other/file.md": b"y"}, when="2021-06-01T00:00:00+00:00")

    merged = datetime(2021, 5, 12, 16, 25, 28, tzinfo=UTC)
    assert merge_time(repo.path, previous, current, PATHS) == merged
    assert merge_time(repo.path, None, current, PATHS) == merged


def test_a_git_failure_raises_with_the_git_error(make_git_repo: Callable[[str], Any]) -> None:
    repo = make_git_repo("website")
    repo.commit({"a.md": PAGE})
    missing = Snapshot(24, "release-1.24", "0" * 40)

    with pytest.raises(GitError, match=r"not a tree object|Not a valid object name"):
        read_files(repo.path, ["docs/"], [missing], (".md",))


# --- Similarity renames between two snapshots (S05-T2) -----------------------------------------

TEN_LINES = b"".join(b"line %d of the page\n" % n for n in range(10))  # 19 bytes a line


def test_similar_renames_pairs_files_at_least_half_similar_among_the_given_paths(
    make_git_repo: Callable[[str], Any],
) -> None:
    repo = make_git_repo("website")
    other = b"".join(b"other line %d\n" % n for n in range(10))  # 13 bytes a line
    before = repo.commit({"docs/old.md": TEN_LINES, "docs/gone.md": TEN_LINES, "docs/b.md": other})
    after = repo.commit(
        {
            # Keeps 6 of old.md's 10 lines (then a "line 6" fragment): 114 of 190 bytes, 60%.
            "docs/old.md": None,
            "docs/new.md": TEN_LINES[:120] + b"rewritten\n" * 4,
            # Keeps 4 of b.md's 10 lines (then "othe"): 52 of the larger file's 164 bytes, ~31%.
            "docs/b.md": None,
            "docs/c.md": other[:56] + b"changed text here\n" * 6,
            # A 100% rename, but outside the given paths.
            "docs/gone.md": None,
            "docs/moved.md": TEN_LINES,
        }
    )

    paths = ["docs/old.md", "docs/new.md", "docs/b.md", "docs/c.md"]
    assert similar_renames(repo.path, before, after, paths) == [("docs/old.md", "docs/new.md")]


def test_similar_renames_without_paths_reads_nothing(make_git_repo: Callable[[str], Any]) -> None:
    repo = make_git_repo("website")
    before = repo.commit({"docs/a.md": TEN_LINES})
    after = repo.commit({"docs/a.md": None, "docs/b.md": TEN_LINES})

    # An empty pathspec would diff the whole tree; no paths means no renames.
    assert similar_renames(repo.path, before, after, []) == []


GATE_FIXTURES = Path(__file__).parents[1] / "fixtures" / "website_s05" / "feature-gates"


@pytest.mark.parametrize(
    ("old", "new", "renamed"),
    [
        # The gate renamed in the docs at 1.33: git scores the real pair 93% (spike §4 E).
        ("APIServingWithRoute/1.32.md", "APIServingWithRoutine/1.33.md", True),
        # Two different gates, 1.36 -> 1.37: 40%, from the shared front matter (spike §4 E).
        ("PodInfoAPI/1.36.md", "InPlacePodVerticalScalingMemoryBackedVolumes/1.37.md", False),
    ],
)
def test_similar_renames_on_real_gate_files(
    make_git_repo: Callable[[str], Any], old: str, new: str, renamed: bool
) -> None:
    repo = make_git_repo("website")
    old_path, new_path = f"gates/{old.split('/')[0]}.md", f"gates/{new.split('/')[0]}.md"
    before = repo.commit({old_path: (GATE_FIXTURES / old).read_bytes()})
    after = repo.commit({old_path: None, new_path: (GATE_FIXTURES / new).read_bytes()})

    found = similar_renames(repo.path, before, after, [old_path, new_path])

    assert found == ([(old_path, new_path)] if renamed else [])


SIG_RELEASE_FIXTURES = Path(__file__).parents[1] / "fixtures" / "sig_release"


def test_similar_renames_pairs_the_real_go_handbook_move(
    make_git_repo: Callable[[str], Any],
) -> None:
    # sig-release PR #2984 (1.36 -> 1.37) moved handbooks/go.md to go-updates.md and rewrote
    # part of it: git scores the real pair 66% (S05-R2 sitting), so the governance doc is linked.
    repo = make_git_repo("sig-release")
    old, new = "release-engineering/handbooks/go.md", "release-engineering/handbooks/go-updates.md"
    before = repo.commit({old: (SIG_RELEASE_FIXTURES / "go" / "1.36.md").read_bytes()})
    after = repo.commit(
        {old: None, new: (SIG_RELEASE_FIXTURES / "go-updates" / "1.37.md").read_bytes()}
    )

    assert similar_renames(repo.path, before, after, [old, new]) == [(old, new)]
