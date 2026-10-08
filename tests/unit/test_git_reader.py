"""Reading snapshots from git: which files are read, skipped, and when commits happened.

Every repo here is a tiny local one built by the test (no network).
"""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest

from orgknow.ingestion.git_reader import (
    GitError,
    commit_times,
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


def test_commit_times_lists_only_commits_touching_the_files_since_the_previous_snapshot(
    make_git_repo: Callable[[str], Any],
) -> None:
    repo = make_git_repo("enhancements")
    previous = repo.commit({"kep/README.md": b"v1"}, when="2022-06-01T17:05:45-07:00")
    repo.commit({"kep/README.md": b"v2"}, when="2022-08-31T15:51:14-04:00")
    repo.commit({"other/file.md": b"x"}, when="2022-09-01T00:00:00+00:00")
    current = repo.commit({"kep/kep.yaml": b"stage: beta\n"}, when="2022-09-22T10:28:05+02:00")
    paths = ["kep/README.md", "kep/kep.yaml"]

    since_previous = commit_times(repo.path, previous, current, paths)
    whole_history = commit_times(repo.path, None, current, paths)

    assert sorted(since_previous) == [
        datetime(2022, 8, 31, 19, 51, 14, tzinfo=UTC),
        datetime(2022, 9, 22, 8, 28, 5, tzinfo=UTC),
    ]
    assert min(whole_history) == datetime(2022, 6, 2, 0, 5, 45, tzinfo=UTC)
    assert len(whole_history) == 3


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
