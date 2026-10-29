"""S02-T4a spike: git rename detection between adjacent website releases, graded against
independent oracles. Blog identity is T4b.

Run: uv run python spikes/renames.py

- Renames: `git diff -M10% --name-status` between the locked website snapshots of adjacent
  releases, over the in-scope .md files of the release-scoped website sources (docs pages, release
  records, feature gates). git pairs greedily from the highest score down, so a pair scored s% is
  found at every threshold up to s: one run at the floor gives the counts for every threshold.
- Oracles: docs pages and release records use the site's static/_redirects (Netlify: old URL ->
  new URL) at the newer release and the new page's Hugo `aliases`. Feature gates use the
  front-matter `title` (the gate name) before and after.

Downloads only static/_redirects per release; the .md contents are local since T3a.
Throwaway spike code (S02; see docs/research/corpus-spike-report.md): never imported by src/.
"""

from __future__ import annotations

import random
import re
from collections import Counter
from itertools import pairwise
from pathlib import PurePosixPath
from typing import Any, NamedTuple

import yaml
from fetch import LOCK, MANIFEST, cache_dir_or_exit, git
from measure import ls_tree, md_table, prefetch, read_blobs, split_front_matter

FLOOR = 10  # git -M floor, in percent
THRESHOLDS = (100, 90, 70, 60, 50, 30, 10)  # 60 is ADR-002 D4's starting value
SAMPLE_SIZE, SAMPLE_SEED = 6, 4  # inexact feature-gate renames to read by hand
# From 1.34 the site builds _redirects from a template that copies in _redirects.base whole.
REDIRECTS = ("static/_redirects", "static/_redirects.base")
SPLIT = ("1.28", "1.29")  # feature gates: one table page became one file per gate (T3a)
GATE_COLS = ("renames", "deletes", "adds", "missed renames")
# Hand-read verdicts that override the title oracle (report §4): the gate name was a typo fix.
HAND_VERDICTS = {("APIServingWithRoute", "APIServingWithRoutine"): True}


class Change(NamedTuple):
    status: str  # A, D, M or R
    score: int | None  # similarity in percent, for R
    old: str | None
    new: str | None


def parse_name_status(out: str) -> list[Change]:
    """`git diff`/`git log` with --name-status -z: a status token, then one path (two for R)."""
    tokens = (t.lstrip("\n") for t in out.split("\0"))
    changes = []
    for token in tokens:
        if not token:
            continue
        status, score = token[0], int(token[1:]) if token[1:] else None
        old = new = next(tokens)
        if status == "R":
            new = next(tokens)
        changes.append(
            Change(status, score, None if status == "A" else old, new if status != "D" else None)
        )
    return changes


def norm_url(url: str) -> str:
    """Site-relative, lowercase (Hugo lowercases paths), no fragment or query, trailing slash."""
    url = re.sub(r"^https?://kubernetes\.io", "", url).split("#")[0].split("?")[0].lower()
    return url if url.endswith("/") else url + "/"


def page_url(path: str) -> str:
    """The URL Hugo serves a content/en file at. `_index.md` and `index.md` are their directory."""
    page = PurePosixPath(path.removeprefix("content/en"))
    page = page.parent if page.stem in ("_index", "index") else page.with_suffix("")
    return norm_url(str(page))


def parse_redirects(text: str) -> dict[str, str]:
    """static/_redirects lines are `<from> <to> [status]`. Netlify applies the first matching
    rule, so the first rule per source wins. Wildcard (*) and placeholder (:x) rules are skipped."""
    redirects: dict[str, str] = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 2 and not fields[0].startswith("#") and not re.search("[*:]", fields[0]):
            redirects.setdefault(norm_url(fields[0]), norm_url(fields[1]))
    return redirects


def aliases(meta: dict[str, Any] | None) -> set[str]:
    """Hugo `aliases` front matter: old URLs that redirect to this page."""
    raw = (meta or {}).get("aliases") or []
    return {norm_url(a) for a in ([raw] if isinstance(raw, str) else raw) if isinstance(a, str)}


def classify_delete(
    old_url: str,
    redirects: dict[str, str],
    added_in_scope: set[str],
    added_elsewhere: set[str],
    existing: set[str],
) -> str:
    """Why a deleted page has no rename partner, from where its URL redirects at the newer
    release. Only a target added in the same release is a move; an older target is a removal."""
    target = redirects.get(old_url)
    if target is None:
        return "removed, no redirect"
    if target in added_in_scope:
        return "missed rename"
    if target in added_elsewhere:
        return "moved out of scope"
    if target in existing:
        return "removed, redirected to an older page"
    return "redirect target not found"


def threshold_counts(
    scored: list[tuple[int, bool]], thresholds: tuple[int, ...]
) -> list[tuple[int, int, int, int]]:
    """(threshold, detected, real, wrong) from the renames found at the floor, with verdicts."""
    rows = []
    for t in thresholds:
        found = [real for score, real in scored if score >= t]
        rows.append((t, len(found), sum(found), len(found) - sum(found)))
    return rows


# --- Run --------------------------------------------------------------------------------------


def short(path: str | None) -> str:
    return (path or "").removeprefix("content/en/docs/").removeprefix("content/en/")


def print_thresholds(group: str, scored: list[tuple[int, bool]], missed_any: int) -> None:
    rows, prev = [], (0, 0)
    floor_real = sum(real for _, real in scored)
    for t, found, real, wrong in threshold_counts(scored, THRESHOLDS):
        precision = f"{real / found:.1%}" if found else "-"
        missed = floor_real - real + missed_any
        rows.append(
            [f"{t}%", found, real, wrong, precision, real - prev[0], wrong - prev[1], missed]
        )
        prev = (real, wrong)
    print(f"\n#### {group}\n")
    head = ["threshold", "detected", "real", "wrong", "precision", "real gained", "wrong added"]
    print(md_table([*head, "real missed"], rows))


def main() -> None:
    cache = cache_dir_or_exit()
    website = cache / "website"
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    src = manifest["sources"]
    versions = [r["version"] for r in manifest["releases"]["list"]]
    shas = {v: lock["website_releases"][v]["sha"] for v in versions}
    gate_paths = src["feature_gate_reference"]["paths"]
    rr_website, _ = src["release_record"]
    scope = [p for ps in src["docs_page"]["sigs"].values() for p in ps]
    scope += [*rr_website["paths"], *gate_paths]
    pathspecs = [f"{p}*.md" if p.endswith("/") else p for p in scope]

    def is_gate(path: str | None) -> bool:
        return any((path or "").startswith(p) for p in gate_paths)

    # In-scope .md files per release, and every content/en page (tree listings, no contents).
    files = {
        v: {p: o for p, o in ls_tree(website, shas[v], scope).items() if p.endswith(".md")}
        for v in versions
    }
    pages = {
        v: {p for p in ls_tree(website, shas[v], ["content/en/"]) if p.endswith(".md")}
        for v in versions
    }
    redirect_oids = {}
    for v in versions[1:]:
        found = ls_tree(website, shas[v], list(REDIRECTS))
        redirect_oids[v] = found.get(REDIRECTS[0]) or found[REDIRECTS[1]]
    prefetch(website, sorted(set(redirect_oids.values())))
    oids = set(redirect_oids.values()) | {o for fs in files.values() for o in fs.values()}
    texts = read_blobs(website, sorted(oids))

    def meta(v: str, path: str) -> dict[str, Any]:
        return split_front_matter(texts[files[v][path]])[0] or {}

    doc_renames, gate_renames, unmatched, gate_rows = [], [], [], []
    missed = Counter[str]()
    for va, vb in pairwise(versions):
        pair = f"{va}→{vb}"
        diff_args = [f"-M{FLOOR}%", "--name-status", "-z", shas[va], shas[vb], "--", *pathspecs]
        diff = git("diff", *diff_args, repo=website)
        changes = [c for c in parse_name_status(diff) if c.status != "M"]
        redirects = parse_redirects(texts[redirect_oids[vb]])
        alias_map = {
            a: page_url(p) for p in files[vb] if not is_gate(p) for a in aliases(meta(vb, p))
        }
        merged = alias_map | redirects  # _redirects wins over an alias for the same URL
        added_pages, deleted_pages = pages[vb] - pages[va], pages[va] - pages[vb]
        in_scope_adds = {page_url(c.new) for c in changes if c.status == "A" and c.new}
        elsewhere = {page_url(p) for p in added_pages if p not in files[vb]}
        existing = {page_url(p) for p in pages[vb] - added_pages}
        deleted_urls = {page_url(p) for p in deleted_pages}
        in_scope_deletes = {page_url(c.old) for c in changes if c.status == "D" and c.old}
        gate_adds = {
            meta(vb, c.new).get("title") for c in changes if c.status == "A" and is_gate(c.new)
        }
        n_gate = Counter[str]()
        for c in changes:
            if c.status == "R" and c.old and c.new and c.score is not None:
                if is_gate(c.new):
                    title_a, title_b = meta(va, c.old).get("title"), meta(vb, c.new).get("title")
                    same = bool(title_a) and title_a == title_b
                    real = HAND_VERDICTS.get((title_a, title_b), same)
                    gate_renames.append((pair, c, title_a, title_b, real))
                    n_gate["renames"] += 1
                else:
                    old_url, new_url = page_url(c.old), page_url(c.new)
                    by_redirect, by_alias = (
                        redirects.get(old_url) == new_url,
                        old_url in aliases(meta(vb, c.new)),
                    )
                    doc_renames.append(
                        (pair, c, redirects.get(old_url), by_alias, by_redirect or by_alias)
                    )
            elif is_gate(c.old or c.new):
                n_gate["adds" if c.status == "A" else "deletes"] += 1
                title = meta(va, c.old).get("title") if c.status == "D" and c.old else None
                if title and title in gate_adds:
                    n_gate["missed renames"] += 1
            elif c.status == "D" and c.old:
                url = page_url(c.old)
                kind = classify_delete(url, merged, in_scope_adds, elsewhere, existing)
                missed["docs"] += kind == "missed rename"
                unmatched.append((pair, "deleted", short(c.old), kind, short(merged.get(url))))
            elif c.status == "A" and c.new:
                sources = [
                    s for s, t in merged.items() if t == page_url(c.new) and s in deleted_urls
                ]
                kind = "new page"
                if sources:  # a source deleted in scope is the other half of a missed rename
                    in_scope = any(s in in_scope_deletes for s in sources)
                    kind = "missed rename" if in_scope else "moved in from out of scope"
                unmatched.append((pair, "added", short(c.new), kind, ", ".join(sources)))
        missed["gates"] += n_gate["missed renames"]
        if n_gate:
            gate_rows.append([pair, *(n_gate[col] for col in GATE_COLS)])
        if (va, vb) == SPLIT:
            adds = [c.new for c in changes if c.status == "A" and is_gate(c.new) and c.new]
            titles = [str(meta(vb, p).get("title", "")) for p in adds]
            others = [c for c in changes if is_gate(c.old or c.new) and c.status != "A"]
            single = [texts[o] for p, o in files[va].items() if p in gate_paths]  # 1.28 pages
            print_split(adds, titles, others, "\n".join(single))

    print("\n### Docs and release-record renames\n")
    rows = [
        [p, c.score, short(c.old), short(c.new), short(t), by_alias, real]
        for p, c, t, by_alias, real in doc_renames
    ]
    print(md_table(["pair", "score", "old", "new", "redirect target", "alias", "real"], rows))
    print("\n### Unmatched docs and release-record adds and deletes\n")
    print(md_table(["pair", "change", "path", "class", "redirect"], unmatched))
    print("\nclasses:", dict(Counter((row[1], row[3]) for row in unmatched)))
    print("\n### Feature gates per pair (title oracle)\n")
    print(md_table(["pair", *GATE_COLS], gate_rows))
    mismatches = [
        (p, c.score, short(c.old), short(c.new), a, b, real)
        for p, c, a, b, real in gate_renames
        if a != b
    ]
    print(f"\ngate renames: {len(gate_renames)}; title mismatches (pair, ..., verdict):")
    print(*mismatches, sep="\n")
    inexact = sorted(
        (p, c.score, short(c.old), short(c.new), a, b)
        for p, c, a, b, _ in gate_renames
        if c.score is not None and c.score < 100
    )
    sample = random.Random(SAMPLE_SEED).sample(inexact, min(SAMPLE_SIZE, len(inexact)))
    print(f"\nhand-read sample ({len(sample)} of {len(inexact)} inexact gate renames):")
    print(md_table(["pair", "score", "old", "new", "title before", "title after"], sample))

    print("\n### Thresholds")
    print_thresholds(
        "docs + release records", [(c.score, r) for _, c, _, _, r in doc_renames], missed["docs"]
    )
    print_thresholds(
        "feature gates", [(c.score, r) for _, c, _, _, r in gate_renames], missed["gates"]
    )


def print_split(adds: list[str], titles: list[str], others: list[Change], page: str) -> None:
    """The 1.28→1.29 feature-gate change: what git reports, and whether the new per-gate files'
    gate names (titles) were rows of the old single page."""
    print(f"\n### Feature-gate split {SPLIT[0]}→{SPLIT[1]}\n")
    print("other gate changes:", [(c.status, c.score, short(c.old), short(c.new)) for c in others])
    print("adds by folder:", dict(Counter(PurePosixPath(p).parent.name for p in adds)))
    pages = [
        (short(p), t)
        for p, t in zip(adds, titles, strict=True)
        if PurePosixPath(p).name in ("index.md", "_index.md")
    ]
    print("adds that are page files (index.md), with titles:", pages)
    on_page = sum(bool(t and re.search(rf"\b{re.escape(t)}\b", page)) for t in titles)
    print(f"gate names found in the {SPLIT[0]} single pages: {on_page} of {len(adds)}")


if __name__ == "__main__":
    main()
