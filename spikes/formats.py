"""S02-T5a spike: feature-gate format checks. Does the feature-gates reference give a stage per
version, and do the pre-1.29 tables agree with the 1.29+ per-gate `stages:` ranges?

Run: uv run python spikes/formats.py

- 1.20-1.28: feature-gates.md (plus feature-gates-removed.md from 1.25) holds markdown tables
  with one row per gate and stage: Feature | Default | Stage | Since | Until (From | To on the
  removed page).
- 1.29+: one file per gate under feature-gates/ and feature-gates-removed/, with a `stages:` list
  in its front matter. The gate is the front-matter title (T4a), not the file name.
- A range includes both ends. An empty Until or a missing toVersion means the stage is current.

Reads the locked website snapshots. The contents are local since T3a, so nothing new downloads.
Throwaway spike code (docs/slices/S02-corpus-spike.md): never imported by src/.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from itertools import pairwise
from typing import Any

import yaml
from fetch import LOCK, MANIFEST, cache_dir_or_exit
from measure import ls_tree, md_table, prefetch, read_blobs, split_front_matter

TABLE_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|[^|]*\|([^|]*)\|([^|]*)\|([^|]*)\|")
TABLE_PAGES = ("/feature-gates.md", "/feature-gates-removed.md")  # main page first
VERSION = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?(?:-(alpha|beta|rc)\.(\d+))?")
PRE_RELEASE = {"alpha": 0, "beta": 1, "rc": 2, None: 3}  # a release sorts after its pre-releases
STAGE_SYNONYMS = {"ga": "stable"}  # the tables say GA, the per-gate files say stable
COMPARED_AT, COMPARED_WITH = "1.28", "1.37"  # the last table release, the latest file release
EVERY_MINOR = [f"1.{minor}" for minor in range(29)]  # 1.0-1.28, the history the tables cover
EXAMPLES = (
    "PodSecurity",  # KEP-2579
    "LegacyServiceAccountTokenNoAutoGeneration",  # KEP-2799
    "LegacyServiceAccountTokenTracking",  # KEP-2799
    "LegacyServiceAccountTokenCleanUp",  # KEP-2799
)

Range = tuple[str, str | None, str | None]  # (stage, from, to); a None `to` is still current


def version_key(text: str) -> tuple[int, int, int, int, int] | None:
    """(major, minor, patch, pre-release rank, pre-release number), or None if `text` isn't a
    version. Numeric, so 1.9 < 1.10, and v1.37.0-alpha.1 < -beta.0 < -rc.1 < v1.37.0."""
    match = VERSION.fullmatch(text.strip())
    if match is None:
        return None
    major, minor, patch, pre, number = match.groups()
    return (int(major), int(minor), int(patch or 0), PRE_RELEASE[pre], int(number or 0))


def norm_stage(stage: str) -> str:
    """Case and whitespace, plus GA = stable. Any other value is kept as is, so it shows up."""
    stage = stage.strip().lower()
    return STAGE_SYNONYMS.get(stage, stage)


def gate_table_rows(text: str) -> dict[str, list[Range]]:
    """{gate: its rows in page order} from a pre-1.29 table page. An open Until is None: the
    tables write it as an empty cell or as `-`."""
    gates: dict[str, list[Range]] = defaultdict(list)
    for line in text.splitlines():
        if match := TABLE_ROW.match(line):
            gate, stage, since, until = (part.strip() for part in match.groups())
            gates[gate].append((stage, since or None, None if until in ("", "-") else until))
    return dict(gates)


def gate_stages(meta: dict[str, Any]) -> list[Range]:
    """[(stage, fromVersion, toVersion)] from a 1.29+ gate file's front matter. Other stage keys
    (defaultValue, locked) are ignored. A missing toVersion is None."""
    stages = meta.get("stages") or []
    return [(str(s.get("stage", "")), s.get("fromVersion"), s.get("toVersion")) for s in stages]


def stage_at(ranges: list[Range], version: str) -> str | None:
    """The stage of the first range containing `version`, ends included; None if none does."""
    at = version_key(version)
    for stage, start, end in ranges:
        lo, hi = version_key(start or ""), version_key(end) if end else None
        if at and lo and lo <= at and (end is None or (hi and at <= hi)):
            return stage
    return None


def range_problems(ranges: list[Range]) -> list[str]:
    """Why a gate's stage at some release would be undefined or ambiguous. Ranges are taken in
    page order, and each must start at the release after the previous one ends: the next minor,
    or the next patch when the previous one ends at a patch."""
    spans = []
    for _, start, end in ranges:
        lo, hi = version_key(start or ""), version_key(end) if end else None
        if lo is None or (end and hi is None):
            return ["unparseable version"]
        spans.append((lo, hi))
    problems = ["ends before it starts" for lo, hi in spans if hi and hi < lo]
    for (_, prev_end), (start, _) in pairwise(spans):
        if prev_end is None:
            problems.append("open range not last")
        elif start <= prev_end:
            problems.append("overlap")
        else:
            major, minor, patch = prev_end[:3]
            if start[:3] not in ((major, minor, patch + 1), (major, minor + 1, 0)):
                problems.append("gap")
    return problems


def gate_ranges(files: dict[str, str], texts: dict[str, str]) -> dict[str, list[Range]]:
    """{gate: ranges} for one release: from the table pages, or from the per-gate files."""
    gates: dict[str, list[Range]] = defaultdict(list)
    for page in TABLE_PAGES:
        for path, oid in files.items():
            if path.endswith(page):
                for gate, rows in gate_table_rows(texts[oid]).items():
                    gates[gate] += rows
    for path, oid in files.items():
        if not path.endswith((*TABLE_PAGES, "/index.md")):
            meta = split_front_matter(texts[oid])[0] or {}
            gates[str(meta.get("title"))] += gate_stages(meta)
    return dict(gates)


def norm_at(ranges: list[Range], version: str) -> str | None:
    """The normalized stage at `version`, or None."""
    stage = stage_at(ranges, version)
    return norm_stage(stage) if stage else None


def first_difference(a: list[Range], b: list[Range], versions: list[str]) -> str | None:
    """The first version at which `a` and `b` give a different stage, or None if they agree."""
    return next((v for v in versions if norm_at(a, v) != norm_at(b, v)), None)


def show(ranges: list[Range]) -> str:
    return ", ".join(f"{stage} {start}-{end or ''}" for stage, start, end in ranges) or "none"


def main() -> None:
    cache = cache_dir_or_exit()
    website = cache / "website"
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    lock = yaml.safe_load(LOCK.read_text(encoding="utf-8"))
    paths = manifest["sources"]["feature_gate_reference"]["paths"]
    listings = {}
    for release in manifest["releases"]["list"]:
        sha = lock["website_releases"][release["version"]]["sha"]
        files = ls_tree(website, sha, paths)
        listings[release["version"]] = {p: o for p, o in files.items() if p.endswith(".md")}
    oids = sorted({oid for files in listings.values() for oid in files.values()})
    prefetch(website, oids)  # a no-op since T3a; keeps a fresh cache working
    texts = read_blobs(website, oids)
    by_release = {v: gate_ranges(files, texts) for v, files in listings.items()}
    tabled = {v for v, files in listings.items() if any(p.endswith(TABLE_PAGES) for p in files)}

    print("\n### Feature gates per release\n")
    rows = []
    for v, gates in by_release.items():
        values = Counter(stage.strip() for ranges in gates.values() for stage, _, _ in ranges)
        problems = Counter(p for ranges in gates.values() for p in set(range_problems(ranges)))
        rows.append(
            [
                v,
                "tables" if v in tabled else "per-gate files",
                len(gates),
                sum(1 for ranges in gates.values() if ranges),
                ", ".join(f"{s} {n}" for s, n in values.most_common()),
                ", ".join(f"{p} {n}" for p, n in problems.most_common()) or "none",
            ]
        )
    header = ["release", "format", "gates", "with ranges", "stage values", "gates with a problem"]
    print(md_table(header, rows))
    seen = set()  # print each problem listing once, at the first release that has it
    for v, gates in by_release.items():
        for gate, ranges in sorted(gates.items()):
            if (problems := range_problems(ranges)) and (gate, show(ranges)) not in seen:
                seen.add((gate, show(ranges)))
                print(f"- from {v}, `{gate}`: {', '.join(problems)}: {show(ranges)}")

    old, new = by_release[COMPARED_AT], by_release[COMPARED_WITH]
    both = sorted(old.keys() & new.keys())
    print(f"\n### Agreement: the {COMPARED_AT} tables vs the {COMPARED_WITH} files\n")
    verdicts: dict[str, list[str]] = defaultdict(list)
    for gate in both:
        a, b = norm_at(old[gate], COMPARED_AT), norm_at(new[gate], COMPARED_AT)
        if a == b:
            verdicts["same stage" if a else "no stage in either"].append(gate)
        else:
            verdicts["different stage" if a and b else "a stage on one side only"].append(gate)
    rows = [[k, len(gates), ", ".join(gates[:3])] for k, gates in verdicts.items()]
    print(md_table([f"at {COMPARED_AT}", "gates", "examples"], rows))
    via_ga = [g for g in verdicts["same stage"] if stage_at(old[g], COMPARED_AT) == "GA"]
    print(f"\n- gates in both: {len(both)}; same stage via GA = stable: {len(via_ga)}")
    print(f"- in the {COMPARED_AT} tables only: {sorted(old.keys() - new.keys())}")
    print(f"- in the {COMPARED_WITH} files only: {len(new.keys() - old.keys())}")
    differ = {g: v for g in both if (v := first_difference(old[g], new[g], EVERY_MINOR))}
    print(
        f"- same stage at every minor 1.0-{COMPARED_AT}: {len(both) - len(differ)} of {len(both)}"
    )
    for gate, v in differ.items():
        print(f"  - `{gate}` from {v}: tables {show(old[gate])} | files {show(new[gate])}")

    table_gates = {g for v in tabled for g in by_release[v]}
    file_gates = {g for v in by_release.keys() - tabled for g in by_release[v]}
    only = table_gates - file_gates
    print(f"- gates only in the pre-1.29 tables: {len(only)} of {len(table_gates)}")
    for gate in sorted(only):
        last = max((v for v in tabled if gate in by_release[v]), key=version_key)
        print(f"  - `{gate}`, last in the {last} tables: {show(by_release[last][gate])}")

    print("\n### In-scope examples\n")
    rows = []
    for g in EXAMPLES:
        a, b = old.get(g, []), new.get(g, [])
        rows.append([f"`{g}`", show(a), show(b), first_difference(a, b, EVERY_MINOR) or "none"])
    header = ["gate", f"{COMPARED_AT} tables", f"{COMPARED_WITH} files", "first difference"]
    print(md_table(header, rows))


if __name__ == "__main__":
    main()
