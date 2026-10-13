"""S13-R1 sitting, T2: the free checks on a gold-chains file, before it's copied in.

The S13-R1 contract's loader rules (Pinned: T4), checked independently of src/:
- steps from the 6-step vocabulary, each once; exactly one of texts / not_public /
  not_stored / none; a date on every event step with texts, none on current_docs;
- two steps whose texts share a document: neither whole-document, neither section a
  prefix of the other's (heading by heading, ADR-007 D2);
- every texts entry matches: a stored chunk (canonical id or alias; heading-path prefix),
  or, for a GitHub item T1 hasn't ingested yet, a post section as T1 will render it.
Usage: uv run python eval/results/s13-sitting/check_gold_draft.py <file> <dir of the sitting's JSON>
"""

import datetime
import hashlib
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import label_sheet  # noqa: E402

STEPS = ["problem", "discussion", "proposal", "decision", "implementation", "current_docs"]
FORMS = ["texts", "not_public", "not_stored", "none"]
GH_JSON = {"gh:sig-release/discussions/1290": "disc-1290", "gh:enhancements/issues/2572": "issue-2572",
           "gh:enhancements/pull/2567": "pr-2567", "gh:enhancements/issues/3015": "issue-3015",
           "gh:enhancements/pull/3010": "pr-3010"}


def heads(section: str | None) -> list[str] | None:
    return None if section is None else ([] if section == "" else section.split(" > "))


def prefix(a: list[str], b: list[str]) -> bool:
    return b[: len(a)] == a


def stored_match(doc: str, section: str | None) -> int:
    h = heads(section)
    cond = "" if h is None else (" and c.heading_path = '{}'" if h == [] else
                                 " and c.heading_path[1:%d] = array[%s]" % (len(h), ",".join(
                                     "'" + x.replace("'", "''") + "'" for x in h)))
    sql = ("select count(*) from documents d join document_versions v on v.document_id = d.id "
           "join chunks c on c.document_version_id = v.id "
           f"where (d.canonical_id = '{doc}' or d.id = (select document_id from document_aliases where alias = '{doc}'))"
           + cond)
    out = subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "orgknow", "-d", "orgknow",
                          "-At", "-c", sql], check=True, capture_output=True, text=True).stdout
    return int(out.strip())


def gh_match(doc: str, section: str | None) -> int:
    h = heads(section)
    secs = [p[0].split(" > ") for p in label_sheet.posts(GH_JSON[doc])]
    return len(secs) if h is None else sum(1 for s in secs if prefix(h, s))


def main(path: Path, json_dir: Path) -> int:
    label_sheet.G = json_dir
    data = yaml.safe_load(path.read_text())
    errors: list[str] = []
    for chain in data["chains"]:
        seed, steps = chain["seed"], chain["steps"]
        names = [s["step"] for s in steps]
        if sorted(names, key=STEPS.index) != names or len(set(names)) != len(names) or not set(names) <= set(STEPS):
            errors.append(f"{seed}: steps must be unique, from the vocabulary, in order: {names}")
        if not chain.get("question"):
            errors.append(f"{seed}: no question")
        for s in steps:
            forms = [f for f in FORMS if f in s]
            if len(forms) != 1:
                errors.append(f"{seed} {s['step']}: needs exactly one of {FORMS}, has {forms}")
            dated = isinstance(s.get("date"), datetime.date)
            if s["step"] == "current_docs" and "date" in s:
                errors.append(f"{seed} current_docs: no date expected")
            if s["step"] != "current_docs" and "texts" in s and not dated:
                errors.append(f"{seed} {s['step']}: an event step with texts needs a date")
        labelled = [(s["step"], t["document"], heads(t.get("section"))) for s in steps for t in s.get("texts", [])]
        for i, (sa, da, ha) in enumerate(labelled):
            for sb, db_, hb in labelled[i + 1:]:
                if sa != sb and da == db_ and (ha is None or hb is None or prefix(ha, hb) or prefix(hb, ha)):
                    errors.append(f"{seed}: {sa} and {sb} overlap in {da}: {ha} / {hb}")
        print(f"## {seed} ({chain['role']}): {chain['question']}")
        for s in steps:
            if "texts" not in s:
                form = next(f for f in FORMS if f in s)
                print(f"- {s['step']}: {form}: {s[form]}")
                continue
            print(f"- {s['step']} ({s.get('date', 'undated')}):")
            for t in s["texts"]:
                doc, sec = t["document"], t.get("section")
                n = gh_match(doc, sec) if doc in GH_JSON else stored_match(doc, sec)
                where = "posts (rendered from the sitting's JSON)" if doc in GH_JSON else "stored chunks"
                print(f"  - {n:4d} {where}: {doc}" + (f" › {sec}" if sec is not None else " (whole document)"))
                if n == 0:
                    errors.append(f"{seed} {s['step']}: no match for {doc} › {sec}")
    print("\nsha256:", hashlib.sha256(path.read_bytes()).hexdigest())
    print("errors:", len(errors))
    for e in errors:
        print("  -", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
