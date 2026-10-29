"""S02-T5b spike: CHANGELOG, KEP metadata and blog date formats.

Run: uv run python spikes/source_formats.py

- CHANGELOG: the level-1 sections of each CHANGELOG-1.R.md at the locked kubernetes head. Plus
  one sampled immutability check, not an exhaustive one: CHANGELOG-1.28.md at two pinned
  historical commits (read-only gh api, cached under CORPUS_CACHE_DIR/gh) and at the head.
  Sections are paired by heading, never by position: the files are newest first, so each new
  release is prepended.
- KEP metadata: `status` and `stage` of every distinct kep.yaml under the in-scope SIG dirs,
  across the 19 enhancements snapshots, plus the front matter of the single-file KEPs. Stages are
  classified against both the KEP template and ADR-003 D5's lifecycle_stage. Case and whitespace
  variants normalize; any other value is reported, not mapped.
- Blog: the raw front-matter `date` of the in-scope posts at the website head.

Everything but the gh sample is local since T3a. Throwaway spike code
(S02; see docs/research/corpus-spike-report.md): never imported by src/.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from collections import Counter, defaultdict
from itertools import combinations, zip_longest
from os.path import commonprefix
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from fetch import LOCK, MANIFEST, cache_dir_or_exit
from formats import version_key
from measure import (
    FENCE,
    FRONT_MATTER,
    clean_text,
    load_mapping,
    ls_tree,
    md_table,
    prefetch,
    read_blobs,
    split_front_matter,
)

VERSION_IN_HEADING = re.compile(r"v\d+\.\d+\S*")
TOC = "<!-- BEGIN MUNGE: GENERATED_TOC -->"
SAMPLE = "CHANGELOG/CHANGELOG-1.28.md"
SAMPLE_REFS = {  # kubernetes master commits, found by hand with gh api (report §7)
    "after v1.28.0": "8cb979ae55d1fa4125b9d60d187c9dffa140ccef",  # 2023-08-15
    "after v1.28.15": "6d99b1c843920d71d680df91f4383aadd6337b9d",  # 2024-10-23
}
VERDICTS = ("identical", "identical after clean_text", "changed", "removed", "added")
VERDICTS += ("duplicate heading",)
# The KEP template's values (keps/NNNN-kep-template/kep.yaml); statuses match ADR-003 D5.
STATUSES = ("provisional", "implementable", "implemented", "deferred", "rejected", "withdrawn")
STATUSES += ("replaced",)
# `stage: alpha|beta|stable`, and its comment adds deprecated|disabled|removed for deprecation KEPs.
TEMPLATE_STAGES = ("alpha", "beta", "stable", "deprecated", "disabled", "removed")
LIFECYCLE_STAGES = ("alpha", "beta", "stable", "deprecated", "removed")  # ADR-003 D5


# --- CHANGELOG ------------------------------------------------------------------------------


def changelog_sections(text: str, level: int = 1) -> tuple[str, list[tuple[str, str]]]:
    """(preamble, [(heading, section text)]) in file order, split at headings of `level` outside
    fenced code. The text is kept as is, line endings included. The preamble holds the TOC.
    An indented fence sits in a list item and ends with it, at the next line in column 0: some
    release notes end with a stray closing fence that would otherwise swallow the rest."""
    heading = re.compile(rf"^#{{{level}}}\s+(.+?)\s*$")
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    fence: int | None = None  # the open fence's indentation; None outside a fence
    for line in text.splitlines(keepends=True):
        indent = len(line) - len(line.lstrip(" "))
        if fence and indent == 0 and line.strip():
            fence = None
        if FENCE.match(line):
            fence = indent if fence is None else None
        elif fence is None and (match := heading.match(line)):
            sections.append((match[1], []))
        (sections[-1][1] if sections else preamble).append(line)
    return "".join(preamble), [(h, "".join(lines)) for h, lines in sections]


def duplicate_headings(sections: list[tuple[str, str]]) -> list[str]:
    return [h for h, n in Counter(h for h, _ in sections).items() if n > 1]


def compare_sections(
    old: list[tuple[str, str]], new: list[tuple[str, str]]
) -> dict[str, list[str]]:
    """{verdict: headings} for two versions of one file. Sections are paired by heading, never by
    position, because a new release is prepended. A heading that appears twice on either side
    can't be paired, so it's reported, not compared."""
    dupes = set(duplicate_headings(old)) | set(duplicate_headings(new))
    before, after = dict(old), dict(new)
    verdicts: dict[str, list[str]] = defaultdict(list)
    for heading in [*before, *(h for h in after if h not in before)]:
        a, b = before.get(heading), after.get(heading)
        if heading in dupes:
            verdict = "duplicate heading"
        elif a is None or b is None:
            verdict = "added" if a is None else "removed"
        elif a == b:
            verdict = "identical"
        else:
            same = clean_text(a) == clean_text(b)
            verdict = "identical after clean_text" if same else "changed"
        verdicts[verdict].append(heading)
    return dict(verdicts)


def first_changed_line(a: str, b: str) -> tuple[str, str]:
    """The first pair of lines that differ, ignoring trailing whitespace; "" past the end."""
    pairs = zip_longest(a.splitlines(), b.splitlines(), fillvalue="")
    return next(((x, y) for x, y in pairs if x.rstrip() != y.rstrip()), ("", ""))


def heading_kind(heading: str) -> str:
    return VERSION_IN_HEADING.sub("<v>", heading)


def gh_raw(cache: Path, path: str, sha: str) -> str:
    """A kubernetes/kubernetes file at `sha` via read-only gh api, saved in the corpus cache so a
    re-run is offline. T2's depth-1 clone isn't touched."""
    saved = cache / "gh" / f"{PurePosixPath(path).name}@{sha}"
    if not saved.exists():
        api = f"repos/kubernetes/kubernetes/contents/{path}?ref={sha}"
        cmd = ["gh", "api", "-H", "Accept: application/vnd.github.raw", api]
        print("+", shlex.join(cmd), flush=True)
        saved.parent.mkdir(exist_ok=True)
        saved.write_bytes(subprocess.run(cmd, check=True, stdout=subprocess.PIPE).stdout)
    return saved.read_text(encoding="utf-8")


# --- KEP metadata and blog dates ------------------------------------------------------------


def classify(value: Any, vocabulary: tuple[str, ...]) -> str:
    """A parsed status or stage against a vocabulary. Case and whitespace variants normalize; any
    other value is out of vocabulary: reported, not mapped."""
    if value is None:
        return "missing"
    if not isinstance(value, str):
        return "not a string"
    if value in vocabulary:
        return "in vocabulary"
    return "normalizes" if value.strip().lower() in vocabulary else "out of vocabulary"


def non_string_milestones(meta: dict[str, Any]) -> list[tuple[str, Any]]:
    """Milestone values YAML didn't read as strings: an unquoted 1.30 is the float 1.3, and
    yes/on are booleans (YAML 1.1). Empty values aren't counted."""
    values = [("latest-milestone", meta.get("latest-milestone"))]
    milestone = meta.get("milestone")
    if isinstance(milestone, dict):
        values += [(f"milestone.{k}", v) for k, v in milestone.items()]
    else:
        values.append(("milestone", milestone))
    return [(k, v) for k, v in values if v is not None and not isinstance(v, str)]


def raw_field(text: str, key: str) -> str | None:
    """A top-level YAML key's value as written, quotes kept; keys ignore case."""
    match = re.search(rf"^{re.escape(key)}:[ \t]*(.*?)[ \t]*$", text, re.M | re.I)
    return match[1] if match else None


def date_shape(raw: str | None) -> str:
    """A raw front-matter date with every digit as 9, so the formats can be counted."""
    return "missing" if raw is None else re.sub(r"\d", "9", raw)


# --- Report ---------------------------------------------------------------------------------


def changelogs(manifest: dict[str, Any], lock: dict[str, Any], cache: Path) -> None:
    repo, head = cache / "kubernetes", lock["repos"]["kubernetes"]["head"]
    pattern = manifest["sources"]["release_record"][1]["paths"][0]
    releases = [r["version"] for r in manifest["releases"]["list"]]
    files = ls_tree(repo, head, [pattern.format(version=v) for v in releases])
    prefetch(repo, sorted(files.values()))  # a no-op since T3a; keeps a fresh cache working
    texts = read_blobs(repo, sorted(files.values()))

    print("\n### CHANGELOG sections per file\n")
    rows, kinds, n_sections = [], Counter[str](), 0
    for v in releases:
        preamble, sections = changelog_sections(texts[files[pattern.format(version=v)]])
        minor = tuple(int(part) for part in v.split("."))
        other = [h for h, _ in sections if (key := version_key(h)) is None or key[:2] != minor]
        for _, text in sections:
            kinds.update({heading_kind(h) for h, _ in changelog_sections(text, 2)[1]})
        n_sections += len(sections)
        span = f"{sections[-1][0]} … {sections[0][0]}"
        dupes = ", ".join(duplicate_headings(sections)) or "none"
        rows.append([v, len(sections), span, dupes, ", ".join(other) or "none", TOC in preamble])
    header = ["release", "sections", "oldest … newest", "duplicates", "not a 1.R version", "TOC"]
    print(md_table(header, rows))
    print(f"\n`##` headings, by the sections that have them (of {n_sections}):\n")
    ranked = sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))  # ties by name, so runs match
    print(md_table(["`##` heading", "sections"], ranked))

    print(f"\n### Immutability: {SAMPLE}, one sampled file, not exhaustive\n")
    versions = {
        label: changelog_sections(gh_raw(cache, SAMPLE, sha))[1]
        for label, sha in SAMPLE_REFS.items()
    }
    versions["locked head"] = changelog_sections(texts[files[SAMPLE]])[1]
    rows, listed = [], []
    for a, b in combinations(versions, 2):
        verdicts = compare_sections(versions[a], versions[b])
        rows.append([f"{a} → {b}", *(len(verdicts.get(k, [])) for k in VERDICTS)])
        for heading in verdicts.get("changed", []) + verdicts.get("identical after clean_text", []):
            old, new = dict(versions[a])[heading], dict(versions[b])[heading]
            line_a, line_b = first_changed_line(old, new)
            at = max(len(commonprefix([line_a, line_b])) - 30, 0)  # show where the lines differ
            listed.append(
                f"- {a} → {b}, `{heading}`: {line_a[at : at + 80]!r} → {line_b[at : at + 80]!r}"
            )
    print(md_table(["pair", *VERDICTS], rows))
    print("\n" + "\n".join(listed))


def kep_metadata(manifest: dict[str, Any], lock: dict[str, Any], cache: Path) -> None:
    repo, src = cache / "enhancements", manifest["sources"]["kep"]
    releases = [r["version"] for r in manifest["releases"]["list"]]
    head = lock["repos"]["enhancements"]["head"]
    snapshots = [lock["release_date_snapshots"]["enhancements"][v]["sha"] for v in releases]
    found: dict[str, str] = {}  # blob -> the first path it was found at
    at_head: set[str] = set()
    for sha in [*snapshots, head]:
        for path, oid in ls_tree(repo, sha, src["sig_dirs"]).items():
            single = f"{PurePosixPath(path).parent}/" in src["sig_dirs"] and path.endswith(".md")
            if path.endswith("/kep.yaml") or single:
                found.setdefault(oid, path)
                if sha == head:
                    at_head.add(oid)
    prefetch(repo, sorted(found))
    texts = read_blobs(repo, sorted(found))
    metas: dict[str, dict[str, Any]] = {}
    for oid, path in found.items():
        is_yaml = path.endswith(".yaml")
        meta = load_mapping(texts[oid]) if is_yaml else split_front_matter(texts[oid])[0]
        if meta is not None:
            metas[oid] = meta
        else:
            print(f"- no metadata: {path} ({'kep.yaml that does not parse' if is_yaml else '.md'})")
    singles = {oid for oid in metas if found[oid].endswith(".md")}
    n_yaml = len(metas) - len(singles)
    print(f"\nversions with metadata: {n_yaml} kep.yaml, {len(singles)} single-file KEPs")
    print(f"single-file KEP paths: {len({found[oid] for oid in singles})}")

    vocabularies = {
        "status": {"KEP template = ADR-003 D5": STATUSES},
        "stage": {"KEP template": TEMPLATE_STAGES, "ADR-003 D5": LIFECYCLE_STAGES},
    }
    for key, vocabs in vocabularies.items():
        values: dict[str, list[str]] = defaultdict(list)  # the value's repr -> blobs
        for oid, meta in metas.items():
            values[repr(meta.get(key))].append(oid)
        rows = []
        for shown, oids in sorted(values.items(), key=lambda item: -len(item[1])):
            kinds = [classify(metas[oids[0]].get(key), vocab) for vocab in vocabs.values()]
            counts = [len(set(oids) & at_head), len(oids), len(set(oids) & singles)]
            rows.append([f"`{shown}`", *kinds, *counts, found[oids[0]]])
        print(f"\n### KEP `{key}` values\n")
        header = [*vocabs, "at head", "all versions", "single-file", "example"]
        print(md_table(["value", *header], rows))

    trap = [
        (found[oid], k, v) for oid, meta in metas.items() for k, v in non_string_milestones(meta)
    ]
    empty = sum(1 for oid in metas.keys() - singles if metas[oid].get("latest-milestone") is None)
    keys = Counter(
        str(k)
        for m in metas.values()
        if isinstance(m.get("milestone"), dict)
        for k in m["milestone"]
    )
    print(f"\n- milestone values YAML didn't read as strings: {len(trap)} {trap[:5]}")
    print(f"- kep.yaml versions with an empty or missing latest-milestone: {empty} of {n_yaml}")
    print(f"- milestone keys: {dict(keys.most_common())}")

    print("\n### Traced KEPs at the head\n")
    head_files = ls_tree(repo, head, [f"{d}kep.yaml" for d in src["traced"].values()])
    rows = []
    for number, directory in src["traced"].items():
        oid = head_files[f"{directory}kep.yaml"]
        meta, raw = metas[oid], raw_field(texts[oid], "latest-milestone")
        parsed = repr(meta.get("latest-milestone"))
        rows.append([f"KEP-{number}", meta.get("status"), meta.get("stage"), parsed, f"`{raw}`"])
        rows[-1].append(meta.get("milestone"))
    header = ["KEP", "status", "stage", "latest-milestone (parsed)", "(raw)", "milestone"]
    print(md_table(header, rows))


def blog_dates(manifest: dict[str, Any], lock: dict[str, Any], cache: Path) -> None:
    website, src = cache / "website", manifest["sources"]["blog_post"]
    releases = manifest["releases"]["list"]
    since = str(next(r["release_date"] for r in releases if r["version"] == src["from_release"]))
    files = ls_tree(website, lock["repos"]["website"]["head"], src["paths"])
    posts = {path: oid for path, oid in files.items() if path.endswith(".md")}
    texts = read_blobs(website, sorted(set(posts.values())))
    shapes, undated = Counter[str](), []
    for path, oid in posts.items():
        text = texts[oid].removeprefix("﻿").replace("\r\n", "\n").lstrip("\n")
        raw = {str(k).lower(): v for k, v in (split_front_matter(text)[0] or {}).items()}
        if raw.get("date") is None:
            undated.append(path)
        elif str(raw["date"])[:10] >= since and raw.get("draft") is not True:  # T3a's scope
            block = FRONT_MATTER.match(text)
            shapes[date_shape(raw_field(block[1], "date") if block else None)] += 1
    print(f"\n### Blog: front-matter `date` at the head ({sum(shapes.values())} in-scope posts)\n")
    print(md_table(["raw date, digits as 9", "posts"], shapes.most_common()))
    print(f"\n- post files at the head with no front-matter date: {len(undated)} of {len(posts)}")
    print("\n".join(f"  - {path}" for path in sorted(undated)))


def main() -> None:
    cache = cache_dir_or_exit()
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    changelogs(manifest, lock, cache)
    kep_metadata(manifest, lock, cache)
    blog_dates(manifest, lock, cache)


if __name__ == "__main__":
    main()
