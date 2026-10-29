"""Blog posts (ADR-002 D2-D4, S05-R2 decision 5): the URL Hugo serves a post at, the moment it
is first published, and which of its versions are stored.

A post's history is one entry per first-parent commit on website `main` touching its file,
following renames (`git_reader.post_histories`). The site's config (spike §5): the permalink is
in the manifest; `buildFuture` is off and `timeZone` is UTC, so Hugo renders a post only once
its date has passed; a draft is never rendered.

- **Due time** of an entry: none if it's deleted or a draft; else `publishDate`, else the page
  date, else the commit time (a post with no date renders at once).
- **Publication:** the first moment Hugo renders the post: for each entry in order, max(commit
  time, due time), if that is before the next entry's commit (or it's the last entry).
- **Stored versions:** the version live at publication, from the publication moment, then each
  later version from its commit time. A version superseded before publication was never public,
  so it isn't stored. After publication, a deletion or a draft closes the open version.
  Approximation: a version re-dated into the future after publication still starts at its
  commit, and publication assumes the site builds on every merge (ADR-002 D3).

Pure functions: the git log and the files are read by ingestion.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from orgknow.db.models import Release, VersionData
from orgknow.ingestion.history import Observed, date_history
from orgknow.ingestion.manifest import Snapshot
from orgknow.ingestion.normalize import FileState, front_matter_time

FILENAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})-(.+)")  # Hugo's :filename date: 2024-02-22-slug
TOKEN = re.compile(r":(\w+)")  # a permalink token: :year, :slug, ...


def commit_label(sha: str) -> str:
    """A blog commit's label in failure lines: its short SHA (S05-T8)."""
    return sha[:8]


class Commit(Snapshot):
    """A blog post's commit on `main`, as the snapshot of a version. It isn't a locked snapshot,
    so its label is its short SHA, never "head" (S05-T8)."""

    @property
    def label(self) -> str:
        return commit_label(self.sha)


@dataclass(frozen=True)
class Entry:
    """A post at one first-parent commit on website `main` that touches its file."""

    committed: datetime  # committer time, UTC
    sha: str
    path: str  # the post's file at this commit
    state: FileState | None  # its content then; None: deleted by this commit


@dataclass(frozen=True)
class Publication:
    """When a post was first published, and which entry's text went live then."""

    entry: int  # position of the entry live at publication
    at: datetime


def _lowercase_keys(front_matter: Mapping[str, Any]) -> dict[str, Any]:
    """Hugo reads front-matter keys case-insensitively (`publishDate`, `Date`)."""
    return {str(key).lower(): value for key, value in front_matter.items()}


def page_date(metadata: Mapping[str, Any], path: str) -> tuple[datetime | None, str | None]:
    """Hugo's page date in the site's order: front-matter `date`, else the filename's
    `YYYY-MM-DD-` prefix, else `publishDate`, else `lastmod`. Also the slug the filename gives
    after that prefix: only when the date came from the filename too (Hugo's `:filename`)."""
    front_matter = _lowercase_keys(metadata)
    if (at := front_matter_time(front_matter.get("date"))) is not None:
        return at, None
    page = PurePosixPath(path)
    name = page.parent.name if page.stem == "index" else page.stem  # a bundle is its folder
    if (match := FILENAME_DATE.fullmatch(name)) and (at := front_matter_time(match[1])):
        return at, match[2]
    published = front_matter_time(front_matter.get("publishdate"))
    return published or front_matter_time(front_matter.get("lastmod")), None


def due_time(entry: Entry) -> datetime | None:
    """When Hugo would start rendering this entry's text: its `publishDate`, else its page date,
    else at once (its commit time). None if it's deleted or a draft."""
    if entry.state is None:
        return None
    front_matter = _lowercase_keys(entry.state.metadata)
    if front_matter.get("draft") is True:
        return None
    publish_date = front_matter_time(front_matter.get("publishdate"))
    return publish_date or page_date(front_matter, entry.path)[0] or entry.committed


def publication(entries: Sequence[Entry]) -> Publication | None:
    """The first moment Hugo renders the post (ADR-002 D3): for each entry in order, the later
    of its commit and its due time, if that comes before the next entry's commit (or it's the
    last entry). None if the post was never published."""
    for i, entry in enumerate(entries):
        due = due_time(entry)
        if due is None:
            continue
        moment = max(entry.committed, due)
        if i + 1 == len(entries) or moment < entries[i + 1].committed:
            return Publication(i, moment)
    return None


def out_of_scope(entry: Entry, since: datetime) -> str | None:
    """Why a post is out of the blog scope (S05-R2), or None if it's in: the page date of
    the entry live at publication must be on or after `since` (1.20's release date, 00:00 UTC).
    "no date" if it has no page date, "dated before" if it's earlier (S05-T8)."""
    if entry.state is None:  # deleted: never the entry live at publication
        return "no date"
    published_date = page_date(entry.state.metadata, entry.path)[0]
    if published_date is None:
        return "no date"
    return "dated before" if published_date < since else None


def urlize(text: str) -> str:
    """Approximates Hugo's urlize: lowercase, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\-. ]", "", text.lower()).strip().replace(" ", "-")


def hugo_url(metadata: Mapping[str, Any], path: str, permalink: str) -> str | None:
    """The URL Hugo serves a post at, as built (not yet normalized): the front-matter `url`
    (tokens allowed), else `permalink`. `:year`, `:month` and `:day` come from the page date as
    written; `:slug` is the front-matter `slug`, else the filename's, else the title, through
    `urlize`; `:section` is `blog`. None when a token can't be filled (no page date)."""
    front_matter = _lowercase_keys(metadata)
    at, filename_slug = page_date(front_matter, path)
    slug = front_matter.get("slug") or filename_slug or front_matter.get("title") or ""
    values = {"section": "blog", "slug": urlize(str(slug))}
    if at is not None:
        values |= {"year": f"{at:%Y}", "month": f"{at:%m}", "day": f"{at:%d}"}
    pattern = str(front_matter.get("url") or permalink)
    if any(token not in values for token in TOKEN.findall(pattern)):
        return None
    return TOKEN.sub(lambda token: values[token[1]], pattern)


def post_versions(
    repo: str,
    ref: str,
    entries: Sequence[Entry],
    published: Publication,
    releases: Sequence[Release],
) -> list[VersionData]:
    """The stored versions of a published post, oldest first (ADR-002 D2, D3).

    From the entry live at publication on: that version starts at the publication moment, each
    later one at its commit. A deleted or draft entry closes the open version; a later rendered
    one opens a new one. A version is a change of normalized hash, as for every date-scoped
    source (`date_history`). Its snapshot is the entry's commit on `ref`, at its path then.
    """
    observed = []
    for i in range(published.entry, len(entries)):
        entry = entries[i]
        rendered = due_time(entry) is not None  # neither deleted nor a draft
        at = published.at if i == published.entry else entry.committed
        state = entry.state if rendered else None
        observed.append(Observed(Commit(None, ref, entry.sha), state, at))
    return date_history(repo, observed, releases)
