"""S13-R1 sitting, T2: the label sheet for gold chains v0.

Copies an excerpt of every candidate text from its source, so the developer labels from
the sources, not from the builder's rules: stored texts from the dev database (current
version unless noted), GitHub posts from fetch_items.sh's JSON, with each post's section
name as T1's pinned rendering will write it. The output holds GitHub text, so it goes to
a scratch file, never the repo.
Usage: python3 eval/results/s13-sitting/label_sheet.py <dir of the sitting's JSON> > <scratch>/sheet.md
"""

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from expected_posts import is_bot, load  # noqa: E402

G = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
CUT = 320


def clip(text: str, n: int = CUT) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= n else text[:n] + " …"


def db_text(doc: str, section: str | None, version: str = "current", grep: str | None = None) -> str:
    """First chunk of `doc` under `section` (heading-path prefix; holding `grep` if given), with its windows."""
    where = "v.valid_until_date is null" if version == "current" else f"v.valid_from_date::date = '{version}'"
    path = "" if section is None else " and c.heading_path[1:%d] = %s" % (
        len(section.split(" > ")), "array[" + ",".join("'" + h.replace("'", "''") + "'" for h in section.split(" > ")) + "]")
    sql = (f"select v.valid_from_date::date, v.valid_from_release, coalesce(v.valid_until_release::text, 'open'), "
           f"substring(c.text from position(E'\\n\\n' in c.text) + 2) from documents d "
           f"join document_versions v on v.document_id = d.id join chunks c on c.document_version_id = v.id "
           f"where d.canonical_id = '{doc}' and {where}{path}"
           f"{'' if grep is None else ' and c.text ~ ' + chr(39) + grep + chr(39)} order by v.valid_from_date, c.ordinal limit 1")
    out = subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", "orgknow", "-d", "orgknow",
                          "-At", "-F", "\t", "-c", sql], check=True, capture_output=True, text=True).stdout
    if not out.strip():
        return "**NO STORED TEXT MATCHES**"
    start, rfrom, runtil, body = out.split("\t", 3)
    if grep is not None:  # a packed chunk: start the excerpt near the match
        body = "… " + body[max(0, re.search(grep, body).start() - 80):]
    return f"version from {start}, releases 1.{rfrom}–{runtil if runtil == 'open' else '1.' + runtil}: “{clip(body)}”"


def posts(item: str) -> list[tuple[str, str, str]]:
    """(section, date, text) per kept post, as T1 renders them."""
    if item == "disc-1290":
        d = json.loads((G / "disc-1290.json").read_text())["data"]["repository"]["discussion"]
        raw = [(c["author"]["login"], c["createdAt"], c["body"], "") for c in d["comments"]["nodes"]]
        raw += [(r["author"]["login"], r["createdAt"], r["body"], " · reply")
                for c in d["comments"]["nodes"] for r in c["replies"]["nodes"]]
        opening = (d["body"], d["createdAt"], "justaugustus")
    else:
        kind, n = item.split("-")
        top = json.loads((G / f"{item}.json").read_text())
        opening = (top["body"] or "", top["created_at"], top["user"]["login"])
        raw = [(c["user"]["login"], c["created_at"], c["body"], "") for c in load(G / f"{item}-comments.json")]
        reviews = G / f"{item}-reviews-all.json" if (G / f"{item}-reviews-all.json").exists() else G / f"{item}-reviews.json"
        if kind == "pr" and reviews.exists():
            raw += [(r["user"]["login"], r["submitted_at"], r["body"], " · review")
                    for r in load(reviews) if (r["body"] or "").strip()]
    out = [(f"Opening post · @{opening[2]} · {opening[1][:10]}", opening[1][:10], opening[0])]
    for login, at, body, tag in sorted((p for p in raw if not is_bot(p[0])), key=lambda p: p[1]):
        out.append((f"Comments > @{login} · {at[:10]}{tag}", at[:10], body))
    return out


def show_posts(doc: str, item: str, pick=None, head: int = 3, tail: int = 1, letters: str = "") -> None:
    ps = posts(item)
    print(f"- `{doc}`: {len(ps)} posts ({ps[0][1]} → {ps[-1][1]})")
    chosen = [p for p in ps if pick(p)] if pick else ps[: head + 1] + (ps[-tail:] if len(ps) > head + 1 else [])
    for i, (section, _, body) in enumerate(chosen):
        tag = f"**{letters[i]}.** " if letters else ""
        print(f"  - {tag}section `{section}`: “{clip(body, 220)}”")


def show_db(n: str, doc: str, section: str | None, version: str = "current", grep: str | None = None) -> None:
    label = f"`{doc}`" + (f" › `{section}`" if section else " (whole document)")
    print(f"- {'**' + n + '.** ' if n else ''}{label}: {db_text(doc, section, version, grep)}")


prow = re.compile(r"^/(approve|lgtm|hold)", re.M)


def main() -> None:

    print("# Gold chains v0: label sheet (S13-R1 sitting)\n")
    print("For each step, list the acceptable texts (letters), and the date (YYYY-MM-DD) where asked.")
    print("Or mark the step `not public: <url>`, `not stored: <url>` or `none: <why>`. Two steps")
    print("sharing a document need different sections (`Opening post …` vs `Comments`).\n")

    print("## Chain 1: KEP-2572, release cadence (built on)\n")
    print("Control question (fixed, q04): “Why did Kubernetes move to three releases per year?”\n")
    print("### problem (date?)")
    show_posts("gh:sig-release/discussions/1290", "disc-1290", pick=lambda p: p[0].startswith("Opening"))
    print("  → **a.** that opening post")
    show_db("b", "kep:2572", "KEP-2572: Defining the Kubernetes Release Cadence > Motivation")
    print("\n### discussion (date?)")
    show_posts("gh:sig-release/discussions/1290", "disc-1290")
    print("  → **a.** `Comments` (any comment or reply)")
    show_db("b", "kep:2572", "KEP-2572: Defining the Kubernetes Release Cadence > Implementation History > GitHub Discussion")
    print("\n### proposal (date? the KEP's creation-date is 2021-01-21; PR #2567 opened 2021-03-12)")
    show_db("a", "kep:2572", "KEP-2572: Defining the Kubernetes Release Cadence > Summary")
    print("- **b.** `kep:2572` (whole document)")
    show_posts("gh:enhancements/pull/2567", "pr-2567", pick=lambda p: p[0].startswith("Opening"))
    print("  → **c.** that opening post")
    show_posts("gh:enhancements/issues/2572", "issue-2572", pick=lambda p: p[0].startswith("Opening"))
    print("  → **d.** that opening post (the tracking issue)")
    print("\n### decision (date? PR #2567 merged 2021-04-23T15:38:03Z)")
    show_posts("gh:enhancements/pull/2567", "pr-2567", pick=lambda p: bool(prow.search(p[2])), letters="abcdefgh")
    print("\n### implementation (date?)")
    show_db("a", "web:/blog/2021/07/20/new-kubernetes-release-cadence/", None)
    show_db("b", "web:/blog/2021/07/20/new-kubernetes-release-cadence/", "What's changing and when")
    show_db("c", "changelog:1.22", "v1.22.0 > What's New (Major Themes) > Kubernetes release cadence change")
    show_db("d", "web:/blog/2021/08/04/kubernetes-1-22-release-announcement/", None)
    print("  (1.22 was released 2021-08-04)")
    print("\n### current_docs (no date)")
    show_db("a", "web:/releases/release/", "The Release Cycle")
    show_db("b", "sig-release:release-engineering/versioning.md",
            "Kubernetes Release Versioning > Release versioning > Supported releases and component skew")
    show_db("c", "community:contributors/devel/sig-release/release.md",
            "Targeting enhancements, Issues and PRs to Release Milestones > The Release Cycle")

    print("\n## Chain 2: KEP-3015, PreferSameZone / PreferSameNode (held out)\n")
    print("**Write its WHY question** (the control searches for it), e.g. in q04's style.\n")
    print("Stored GitHub items: issue #3015 (tracking) and PR #3010 only. Not stored: PR #3016")
    print("(2021-10-21, unmerged), PR #4931 (2024-10-24, unmerged), PR #5140 (opened 2025-02-06,")
    print("merged 2025-02-11). The KEP's Implementation History:")
    show_db("", "kep:3015", "KEP-3015 PreferSameZone and PreferSameNode Traffic Distribution > Implementation History")
    print("\n### problem (date?)")
    show_posts("gh:enhancements/pull/3010", "pr-3010", pick=lambda p: p[0].startswith("Opening"))
    print("  → **a.** that opening post (PR #3010, “KEP-2086: Add internalTrafficPolicy: PreferLocal”)")
    show_posts("gh:enhancements/issues/3015", "issue-3015", pick=lambda p: p[0].startswith("Opening"))
    print("  → **b.** that opening post (the tracking issue)")
    show_db("c", "kep:3015", "KEP-3015 PreferSameZone and PreferSameNode Traffic Distribution > Motivation")
    print("\n### discussion (date?)")
    show_posts("gh:enhancements/pull/3010", "pr-3010", head=8)
    print("  → **a.** PR #3010 `Comments`")
    show_posts("gh:enhancements/issues/3015", "issue-3015", head=4, tail=2)
    print("  → **b.** issue #3015 `Comments`")
    print("- **c.** not stored: https://github.com/kubernetes/enhancements/pull/3016 or /pull/4931")
    print("\n### proposal (date? the KEP's creation-date is 2025-01-23; PR #5140 opened 2025-02-06)")
    show_db("a", "kep:3015", "KEP-3015 PreferSameZone and PreferSameNode Traffic Distribution > Summary")
    print("- **b.** `kep:3015` (whole document)")
    print("- **c.** not stored: https://github.com/kubernetes/enhancements/pull/5140")
    print("\n### decision (date? PR #5140 merged 2025-02-11)")
    print("- **a.** not stored: https://github.com/kubernetes/enhancements/pull/5140 (its merge)")
    print("\n### implementation (date? 1.33 was released 2025-04-23; the KEP says alpha landed 2025-05-30)")
    show_db("a", "changelog:1.33", "v1.33.0 > Changes by Kind > API Change", grep="PreferSame")
    show_db("b", "gate:PreferSameTrafficDistribution", None, version="2025-04-23")
    show_db("c", "web:/docs/concepts/services-networking/service/", "Virtual IP addressing mechanism > Traffic distribution",
            version="2025-04-23")
    show_db("d", "web:/blog/2025/07/28/kubernetes-v1-34-sneak-peek/", None)
    show_db("e", "web:/blog/2025/12/17/kubernetes-v1-35-release/", "Features graduating to Stable > PreferSameNode traffic distribution")
    print("\n### current_docs (no date)")
    show_db("a", "web:/docs/concepts/services-networking/service/", "Virtual IP addressing mechanism > Traffic distribution control")
    show_db("b", "web:/docs/reference/networking/virtual-ips/", "Traffic distribution control")
    show_db("c", "gate:PreferSameTrafficDistribution", None)


if __name__ == "__main__":
    main()
