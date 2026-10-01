"""S02-T4b spike: blog post identity. Scores ADR-002 D4's front-matter id against the URL Hugo
serves each post at, and places every version before or after the post's publication.

Run: uv run python spikes/blog_identity.py

- Post histories are T3a's: first-parent commits on website main, with git rename detection
  following website PR #53902's year-folder move. Scope as in T3a: the latest version's
  front-matter date is on or after 1.20's release date, and it isn't a draft.
- The site config is read, not assumed: every hugo.toml/config.toml on main since then must give
  the same blog permalink and front-matter date order.
- Publication is the first moment Hugo renders the post (buildFuture is off, timeZone is UTC):
  the live version isn't a draft and its date has passed. The site builds on merge, so this is
  approximate.

Downloads only the config files; the posts and the redirect file are local since T3a/T4a.
Throwaway spike code (docs/slices/S02-corpus-spike.md): never imported by src/.
"""

from __future__ import annotations

import re
import statistics
import sys
import tomllib
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time
from pathlib import PurePosixPath
from typing import Any

import yaml
from fetch import LOCK, MANIFEST, cache_dir_or_exit, git
from measure import (
    blog_log,
    content_hash,
    ls_tree,
    md_table,
    new_versions,
    prefetch,
    read_blobs,
    split_front_matter,
)
from renames import REDIRECTS, aliases, norm_url, parse_redirects

CONFIGS = ["hugo.toml", "config.toml"]  # config.toml was renamed to hugo.toml in 2023
DATE_ORDER = ("date", ":filename", "publishdate", "lastmod")  # what page_date implements
TOKEN = re.compile(r":(\w+)")
FILENAME_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})-(.+)")
PUBLIC = ("live at publication", "after publication")
TIMINGS = ("before publication", "after publication", "never published")
PHASES = (
    "superseded before publication",
    "live at publication",
    "after publication",
    "never public",
)
MOVE_PR = 53902  # website PR that moved the posts into year folders (report §2, finding 1)


def front_time(value: Any) -> datetime | None:
    """A front-matter date or time. One with an offset keeps it, as Hugo does, so the URL uses the
    date as written; one without is in the site's timeZone, UTC. A bare date is midnight."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.strip())
        except ValueError:
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time(), UTC)
    return None


def page_date(meta: dict[str, Any], path: str) -> tuple[datetime | None, str | None]:
    """Hugo's .Date in the site's order (date, :filename, publishDate, lastmod), plus the slug
    Hugo takes from a YYYY-MM-DD-slug filename: only when the date came from there too."""
    if (when := front_time(meta.get("date"))) is not None:
        return when, None
    page = PurePosixPath(path)
    name = page.parent.name if page.stem == "index" else page.stem  # a bundle is its folder
    if (match := FILENAME_DATE.fullmatch(name)) and (when := front_time(match[1])):
        return when, match[2]
    return front_time(meta.get("publishdate")) or front_time(meta.get("lastmod")), None


def publish_time(meta: dict[str, Any], path: str, committed: datetime) -> datetime | None:
    """When Hugo would start rendering this version: its publishDate, else its .Date, else at
    once (the commit). None for a draft."""
    if meta.get("draft") is True:
        return None
    return front_time(meta.get("publishdate")) or page_date(meta, path)[0] or committed


def urlize(text: str) -> str:
    """Approximates Hugo's urlize: lowercase, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\-. ]", "", text.lower()).strip().replace(" ", "-")


def hugo_url(meta: dict[str, Any], path: str, permalink: str) -> str | None:
    """The URL Hugo serves a post at: the front-matter `url` (tokens allowed), else the config
    permalink. :slug is the front-matter slug, else the filename's, else the title. None when a
    token can't be filled."""
    when, file_slug = page_date(meta, path)
    slug = meta.get("slug") or file_slug or meta.get("title") or ""
    values = {"section": "blog", "slug": urlize(str(slug))}
    if when is not None:
        values |= {"year": f"{when:%Y}", "month": f"{when:%m}", "day": f"{when:%d}"}
    pattern = str(meta.get("url") or permalink)
    if any(token not in values for token in TOKEN.findall(pattern)):
        return None
    return norm_url(TOKEN.sub(lambda m: values[m[1]], pattern))


def fm_id(meta: dict[str, Any]) -> tuple[str | None, str | None]:
    """ADR-002 D4's id parts, blog:<date>-<slug>, from the front matter alone."""
    when, slug = front_time(meta.get("date")), meta.get("slug")
    return (f"{when:%Y-%m-%d}" if when else None), (str(slug) if slug else None)


def change_cause(a: tuple[str | None, str | None], b: tuple[str | None, str | None]) -> str:
    """Which id parts changed between two versions; "missing" when one side has none."""
    parts = [
        f"{name} missing" if None in (x, y) else name
        for name, x, y in (("date", a[0], b[0]), ("slug", a[1], b[1]))
        if x != y
    ]
    return " + ".join(parts)


def published_at(live: list[tuple[datetime, datetime | None]]) -> datetime | None:
    """The first moment Hugo renders the post. `live`: (commit time, publish time, or None while
    a draft or deleted), oldest first; each state holds until the next commit."""
    for i, (committed, due) in enumerate(live):
        if due is None:
            continue
        moment = max(committed, due)
        if i + 1 == len(live) or moment < live[i + 1][0]:
            return moment
    return None


def phases(commits: list[datetime], published: datetime | None) -> list[str]:
    """Each version's place relative to publication, from its commit time (oldest first)."""
    if published is None:
        return ["never public"] * len(commits)
    return [
        "after publication"
        if c > published
        else "superseded before publication"
        if i + 1 < len(commits) and commits[i + 1] <= published
        else "live at publication"
        for i, c in enumerate(commits)
    ]


def timing(committed: datetime, published: datetime | None) -> str:
    """A change relative to publication. A change committed at the publication moment is the
    version that goes live, so it counts as before."""
    if published is None:
        return "never published"
    return "before publication" if committed <= published else "after publication"


def blog_settings(config: dict[str, Any]) -> tuple[str | None, tuple[str, ...]]:
    """(blog permalink, front-matter date order) from a site config, in either TOML layout."""
    links = config.get("permalinks", {})
    permalink = links.get("page", {}).get("blog") or links.get("blog")
    return permalink, tuple(config.get("frontmatter", {}).get("date", ()))


def coverage(old: str, final: str, alias_urls: set[str], redirects: dict[str, str]) -> str:
    """Whether an old URL of a post is declared to lead to its final URL."""
    if old in alias_urls:
        return "alias"
    return "redirect" if redirects.get(old) == final else "none"


# --- Run --------------------------------------------------------------------------------------


def score(
    name: str, ids: dict[str, tuple[set[str | None], set[str | None]]], renames: str
) -> list[object]:
    """A table J row. ids: post -> (ids over every commit, ids over the published commits)."""
    published = [pub for _, pub in ids.values() if pub]
    owners = Counter(i for every, _ in ids.values() for i in every if i is not None)
    return [
        name,
        sum(len(every) == 1 and None not in every for every, _ in ids.values()),
        f"{sum(len(pub) == 1 and None not in pub for pub in published)} of {len(published)}",
        sum(n > 1 for n in owners.values()),
        renames,
    ]


def main() -> None:
    cache = cache_dir_or_exit()
    website = cache / "website"
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    head = lock["repos"]["website"]["head"]
    src = manifest["sources"]["blog_post"]
    releases = manifest["releases"]["list"]
    since = str(next(r["release_date"] for r in releases if r["version"] == src["from_release"]))
    strip = frozenset(
        k.lower() for k in manifest["normalization"]["strip_front_matter"]["blog_post"]
    )

    # The config in effect at `since`, then every change to it on main.
    log = ["log", "--first-parent", "--format=%H"]
    commits = git(*log, f"--since={since}T00:00:00Z", head, "--", *CONFIGS, repo=website).split()
    commits += git(*log, "-1", f"--until={since}T00:00:00Z", head, repo=website).split()
    config_oids = {oid for c in commits for oid in ls_tree(website, c, CONFIGS).values()}
    found = ls_tree(website, head, list(REDIRECTS))
    redirect_oid = found.get(REDIRECTS[0]) or found[REDIRECTS[1]]
    # git needs the post contents to follow the year-folder moves, so list without renames first.
    unfollowed = blog_log(cache, head, src["paths"], follow_renames=False)
    oids = {o for entries in unfollowed.values() for _, _, o in entries if o}
    oids |= config_oids | {redirect_oid}
    prefetch(website, sorted(oids))
    texts = read_blobs(website, sorted(oids))
    posts = blog_log(cache, head, src["paths"], follow_renames=True)

    settings = {blog_settings(tomllib.loads(texts[oid])) for oid in config_oids}
    (permalink, order), *rest = settings
    if rest or permalink is None or tuple(k.lower() for k in order) != DATE_ORDER:
        sys.exit(f"refusing: config differs from what this spike implements: {settings}")
    print(f"\nconfig: {len(config_oids)} versions on main since {since}, all {permalink} {order}")
    redirects = parse_redirects(texts[redirect_oid])

    meta: dict[str, dict[str, Any]] = {}
    keys: dict[str, str] = {}  # blob -> ADR-002 D2 normalized hash
    for oid in {o for entries in posts.values() for _, _, o in entries if o}:
        raw, body = split_front_matter(texts[oid])
        meta[oid] = {str(k).lower(): v for k, v in (raw or {}).items()}
        keys[oid] = content_hash(raw, body, strip)

    def in_scope(entries: list[tuple[datetime, str, str | None]]) -> bool:  # T3a's rule
        last = meta[next(o for _, _, o in reversed(entries) if o)]
        return str(last.get("date", ""))[:10] >= since and last.get("draft") is not True

    scoped = {path: entries for path, entries in posts.items() if in_scope(entries)}
    grep = f"--grep=^Merge pull request #{MOVE_PR} "
    moved_at = int(git(*log[:2], "-1", grep, "--format=%ct", head, repo=website))
    changes: dict[tuple[str, str], list[str]] = defaultdict(list)  # (cause, timing) -> posts
    rules: dict[str, dict[str, tuple[set[str | None], set[str | None]]]] = defaultdict(dict)
    version_phases: dict[str, list[str]] = defaultdict(list)  # phase -> posts, one per version
    moves: dict[str, Counter[str]] = defaultdict(Counter)  # kind -> moves, kept id, kept URL
    ahead: list[float] = []  # days that a version live at publication was merged ahead of it
    counts, coverages, listed = Counter[str](), Counter[str](), []
    for path, entries in scoped.items():
        timeline = [(t, None if o is None else publish_time(meta[o], p, t)) for t, p, o in entries]
        published = published_at(timeline)
        if published is None:
            listed.append(f"never published: {path}")
        versions = new_versions([(i, o) for i, (_, _, o) in enumerate(entries)], keys)
        times = [entries[i][0] for i, _ in versions]
        for t, phase in zip(times, phases(times, published), strict=True):
            version_phases[phase].append(path)
            if phase == "live at publication" and published and t < published:
                ahead.append((published - t).total_seconds() / 86400)

        # Identity is checked at every commit, so moves and path-derived URLs are seen.
        present = [(t, p, meta[o]) for t, p, o in entries if o]
        ids = [fm_id(m) for _, _, m in present]
        urls = [hugo_url(m, p, permalink) for _, p, m in present]
        present_phases = phases([t for t, _, _ in present], published)
        first_public = next(
            (i for i, ph in enumerate(present_phases) if ph in PUBLIC), len(present)
        )
        for i in range(1, len(present)):
            when = timing(present[i][0], published)
            if ids[i] != ids[i - 1]:
                changes[(change_cause(ids[i - 1], ids[i]), when)].append(path)
                if when == "after publication":
                    listed.append(f"id changed after publication: {ids[i - 1]} -> {ids[i]}")
            if present[i][1] != present[i - 1][1]:
                moved_by_pr = present[i][0].timestamp() == moved_at
                kind = f"PR #{MOVE_PR}" if moved_by_pr else f"other, {when}"
                same = {"same id": ids[i] == ids[i - 1], "same URL": urls[i] == urls[i - 1]}
                moves[kind].update({"moves": 1, **same})
                if not all(same.values()) and (moved_by_pr or when != "before publication"):
                    listed.append(f"{kind} move: {ids[i - 1]} {urls[i - 1]} -> {ids[i]} {urls[i]}")
        d4 = [f"blog:{d}-{s}" if d and s else None for d, s in ids]
        rules["D4"][path] = set(d4), set(d4[first_public:])
        rules["A"][path] = {d4[-1]}, ({d4[-1]} if first_public < len(present) else set())
        rules["B"][path] = set(urls), set(urls[first_public:])
        if first_public < len(present) and d4[first_public] != d4[-1]:
            counts["A: latest id differs from the id at publication"] += 1
        final = str(urls[-1])
        old_urls = [str(u) for u in dict.fromkeys(urls[first_public:]) if u != urls[-1]]
        counts["Hugo URL changed after publication"] += bool(old_urls)
        for old in old_urls:
            how = coverage(old, final, aliases(present[-1][2]), redirects)
            coverages[how] += 1
            listed.append(f"old URL ({how}): {old} -> {final}")
        if not present[-1][2].get("slug"):
            listed.append(f"no slug: {path} -> {final}")

    n_changed = len({p for posts_ in changes.values() for p in posts_})
    print(f"posts: {len(posts)} histories, {len(scoped)} in scope, {n_changed} change id")
    print(f"{dict(counts)}; old URLs by what leads to the final URL: {dict(coverages)}")
    causes = sorted(
        {c for c, _ in changes}, key=lambda c: -sum(len(changes[c, t]) for t in TIMINGS)
    )
    rows = [
        [c, *(f"{len(changes[c, t])} ({len(set(changes[c, t]))})" for t in TIMINGS)] for c in causes
    ]
    print("\n### I. Front-matter id changes: transitions (posts)\n")
    print(md_table(["cause", *TIMINGS], rows))

    print("\n### J. Identity rules, over the in-scope post histories\n")
    header = ["rule", "kept whole, every commit", "kept whole, published commits"]
    rows = [
        score("ADR-002 D4 front-matter id, per commit", rules["D4"], "no"),
        score("A: latest date and slug, applied backwards", rules["A"], "yes"),
        score("B: Hugo URL, per commit", rules["B"], "no"),
    ]
    print(md_table([*header, "ids shared by two posts", "needs rename following"], rows))

    print("\n### K. Versions (ADR-002 D2) by publication phase\n")
    rows = [[ph, len(version_phases[ph]), len(set(version_phases[ph]))] for ph in PHASES]
    print(md_table(["phase", "versions", "posts"], rows))
    print(f"\nlive at publication and merged ahead of it: {len(ahead)} versions,", end=" ")
    print(f"median {statistics.median(ahead):.1f} days, max {max(ahead):.1f}")

    print("\n### L. Path changes (moves)\n")
    rows = [[kind, c["moves"], c["same id"], c["same URL"]] for kind, c in sorted(moves.items())]
    print(md_table(["move", "moves", "same front-matter id", "same Hugo URL"], rows))
    print("\n" + "\n".join(listed))


if __name__ == "__main__":
    main()
