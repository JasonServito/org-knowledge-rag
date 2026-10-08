"""Renames (ADR-002 D4): which file at snapshot R+1 continues which file at snapshot R.

Pure functions: ingestion reads the files, the redirect file and git's similarity scores, and
this module decides. A **chain** is one document's file at each snapshot (None where absent).

Release pair by release pair (R -> R+1), a **link** joins a file present at R and gone at R+1 to
a file absent at R and present at R+1. The rules run in order, and the first rule that links a
file wins. Web pages (docs pages, release records, the feature-gates pages):
1. Same URL. This covers page bundles: `x.md` -> `x/index.md`.
2. The redirect file at R+1 maps the gone URL to the new page's URL.
3. The new page's front-matter `aliases` holds the gone URL.
4. git similarity >= 50%, read only for the files no earlier rule linked.

Gate files (one file per feature gate, from 1.29):
1. Same path: the chain builder's own rule. A file at R and R+1 is neither gone nor new.
2. Same front-matter `title`. This covers the 1.32 renames from kebab case to the gate name.
3. The new file's front-matter `former_titles` holds the gone file's title.
4. git similarity >= 50%, as for web pages (`APIServingWithRoute` -> `APIServingWithRoutine`).

Governance docs, read at date snapshots (S05-R2 decision 2; ADR-002 D4):
1. Same path: the chain builder's own rule.
2. git similarity >= 50% between the adjacent snapshots (sig-release PR #2984's 8 moves).

Refused links (their files are left out of the later rules, so they stay unlinked):
- A file that one rule links twice (a gone file claimed by two new files, or the reverse) is a
  conflict.
- A link between two source types is an error.
A redirect to a URL that existed at R is a removal, not a move: a link's target must be new at
R+1 (spike §4 G: `overview.md` -> the section index at 1.29).
"""

import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from orgknow.ingestion.identity import alias_id, docs_canonical_id
from orgknow.ingestion.normalize import decode, docs_state, split_front_matter

# From 1.34 the site builds _redirects at build time and keeps the rules in _redirects.base.
REDIRECT_FILES = ("static/_redirects", "static/_redirects.base")


def norm_url(url: str) -> str:
    """A redirect URL as a site path: no `https://kubernetes.io`, fragment or query; lowercase
    (Hugo lowercases paths); a trailing slash."""
    url = re.sub(r"^https?://kubernetes\.io", "", url).split("#")[0].split("?")[0].lower()
    return url if url.endswith("/") else url + "/"


def parse_redirects(text: str) -> dict[str, str]:
    """The redirect file's rules, `<from> <to> [status]` per line, as {from URL: to URL}.

    Comments, and rules whose source has a wildcard (`*`) or a placeholder (`:x`), are skipped.
    Netlify applies the first matching rule, so the first rule per source wins.
    """
    redirects: dict[str, str] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 2 or fields[0].startswith("#") or re.search("[*:]", fields[0]):
            continue
        redirects.setdefault(norm_url(fields[0]), norm_url(fields[1]))
    return redirects


def page_url(path: str) -> str:
    """The URL Hugo serves a content/en page at, as the redirect file writes it."""
    return docs_canonical_id(path).removeprefix("web:")


@dataclass(frozen=True)
class Pair:
    """One release pair as a link rule sees it: the files no earlier rule has linked."""

    after: int  # position of R+1 in the snapshots
    gone: Mapping[str, bytes]  # present at R, absent at R+1: path -> raw content at R
    new: Mapping[str, bytes]  # absent at R, present at R+1: path -> raw content at R+1


# A link rule returns its candidate links, (gone path, new path).
LinkRule = Callable[[Pair], list[tuple[str, str]]]
# git similarity: (position of R+1, the gone and new paths to compare) -> (gone, new) renames.
SimilarRenames = Callable[[int, Sequence[str]], list[tuple[str, str]]]


@dataclass(frozen=True)
class Link:
    after: int  # position of R+1 in the snapshots
    gone: str  # path at R
    new: str  # path at R+1
    rule: str  # the rule that found it


@dataclass
class Chains:
    """What `build_chains` found. Unmatched files are (position of R+1, path)."""

    paths: list[list[str | None]] = field(default_factory=list)  # per chain: path per snapshot
    links: list[Link] = field(default_factory=list)
    conflicts: list[Link] = field(default_factory=list)  # refused: a file claimed twice
    crossings: list[Link] = field(default_factory=list)  # refused: two source types
    deleted: list[tuple[int, str]] = field(default_factory=list)  # gone and not linked
    added: list[tuple[int, str]] = field(default_factory=list)  # new and not linked


def same_url(pair: Pair) -> list[tuple[str, str]]:
    """Rule 1: the gone file and the new file are served at the same URL."""
    return [(g, n) for g in pair.gone for n in pair.new if page_url(g) == page_url(n)]


def redirect_rule(redirects: Sequence[Mapping[str, str]]) -> LinkRule:
    """Rule 2, given each snapshot's parsed redirect file: the redirect file at R+1 maps the
    gone page's URL to the new page's URL."""

    def by_redirect(pair: Pair) -> list[tuple[str, str]]:
        targets = redirects[pair.after]
        return [
            (g, n) for g in pair.gone for n in pair.new if targets.get(page_url(g)) == page_url(n)
        ]

    return by_redirect


def _alias_ids(path: str, raw: bytes) -> set[str]:
    """The ids of a page's front-matter `aliases`. An empty set if the front matter can't be
    read: the page's document then fails with the reason, when its versions are derived."""
    try:
        return {alias_id(alias) for alias in docs_state(path, raw, frozenset()).aliases}
    except ValueError:
        return set()


def alias_rule(pair: Pair) -> list[tuple[str, str]]:
    """Rule 3: the new page's front-matter `aliases` holds the gone page's URL."""
    links = []
    for n, raw in pair.new.items():
        declared = _alias_ids(n, raw)
        links += [(g, n) for g in pair.gone if docs_canonical_id(g) in declared]
    return links


def web_link_rules(redirects: Sequence[Mapping[str, str]]) -> dict[str, LinkRule]:
    """The declared link rules for web pages, in order. `redirects[i]` is the parsed redirect
    file at the i-th snapshot."""
    return {"same URL": same_url, "redirect": redirect_rule(redirects), "alias": alias_rule}


def _front_matter(raw: bytes) -> dict[str, Any]:
    """A file's front matter, or {} if it can't be read: the file's document then fails with the
    reason, when its versions are derived."""
    try:
        front_matter, _ = split_front_matter(decode(raw))
    except ValueError:
        return {}
    return front_matter


def _titles(files: Mapping[str, bytes]) -> dict[str, object]:
    """Each file's front-matter `title`, for the files that have one."""
    titles = {path: _front_matter(raw).get("title") for path, raw in files.items()}
    return {path: title for path, title in titles.items() if title is not None}


def same_title(pair: Pair) -> list[tuple[str, str]]:
    """Gate rule 2: the gone file and the new file have the same front-matter `title`."""
    gone, new = _titles(pair.gone), _titles(pair.new)
    return [(g, n) for g, title in gone.items() for n, other in new.items() if title == other]


def former_title(pair: Pair) -> list[tuple[str, str]]:
    """Gate rule 3: the new file's front-matter `former_titles` holds the gone file's title."""
    gone = _titles(pair.gone)
    links = []
    for n, raw in pair.new.items():
        former = _front_matter(raw).get("former_titles")
        names = former if isinstance(former, list) else []
        links += [(g, n) for g, title in gone.items() if title in names]
    return links


def gate_link_rules() -> dict[str, LinkRule]:
    """The declared link rules for gate files, in order (rule 1, same path, is the chain
    builder's own). `former_titles` link only a gate whose file is gone: a name in it that keeps
    its own file (`PodHasNetworkCondition`) is never gone, so it links nothing."""
    return {"same title": same_title, "former title": former_title}


def date_link_rules() -> dict[str, LinkRule]:
    """The declared link rules for governance docs: none. Rule 1, same path, is the chain
    builder's own, and git similarity always runs last. Governance docs have no URL, redirect or
    front matter to declare a move (S05-R2 decision 2)."""
    return {}


def _link_pair(
    after: int,
    before: Mapping[str, bytes],
    current: Mapping[str, bytes],
    rules: Mapping[str, LinkRule],
    source_types: Mapping[str, str],
    chains: Chains,
) -> dict[str, str]:
    """Link the files gone at snapshot `after` to the files new there, recording links, refused
    links and unmatched files in `chains`. Returns {new path: gone path}."""
    # A link's target is absent at R, so a redirect to a page that existed at R links nothing.
    gone = {path: before[path] for path in sorted(before.keys() - current.keys())}
    new = {path: current[path] for path in sorted(current.keys() - before.keys())}
    every_gone, every_new = list(gone), list(new)
    linked: dict[str, str] = {}
    for name, rule in rules.items():
        if not gone or not new:
            break
        candidates = sorted(set(rule(Pair(after, gone, new))))
        claims = Counter(path for candidate in candidates for path in candidate)
        for g, n in candidates:
            link = Link(after, g, n, name)
            if claims[g] > 1 or claims[n] > 1:
                chains.conflicts.append(link)
            elif source_types[g] != source_types[n]:
                chains.crossings.append(link)
            else:
                chains.links.append(link)
                linked[n] = g
            # Linked or refused, a file this rule named is left out of the later rules.
            gone.pop(g, None)
            new.pop(n, None)
    chains.deleted += [(after, path) for path in every_gone if path not in linked.values()]
    chains.added += [(after, path) for path in every_new if path not in linked]
    return linked


def build_chains(
    listings: Sequence[Mapping[str, bytes]],
    rules: Mapping[str, LinkRule],
    similar: SimilarRenames,
    source_types: Mapping[str, str],
) -> Chains:
    """Group the files of a source into chains, one per document, across its snapshots (a
    release's branch, or a date snapshot of a default branch).

    `listings[i]` holds every file at the i-th snapshot (path -> raw content). `rules` are the
    declared link rules, in order; git similarity runs last, on the files they left unlinked.
    `source_types` gives each path's source type. A path at two consecutive snapshots stays in
    its chain, and so does a path that comes back after a gap (as before renames).
    """

    def similarity(pair: Pair) -> list[tuple[str, str]]:
        return similar(pair.after, [*pair.gone, *pair.new])

    steps = {**rules, "similarity": similarity}
    chains = Chains()
    latest: dict[str, int] = {}  # path -> the chain whose latest file it is
    for i, files in enumerate(listings):
        linked = (
            {} if i == 0 else _link_pair(i, listings[i - 1], files, steps, source_types, chains)
        )
        for path in sorted(files):
            if path in linked:
                k = latest.pop(linked[path])  # the gone file's chain continues here
            elif path in latest:
                k = latest[path]
            else:
                k = len(chains.paths)
                chains.paths.append([None] * len(listings))
            chains.paths[k][i] = path
            latest[path] = k
    return chains
