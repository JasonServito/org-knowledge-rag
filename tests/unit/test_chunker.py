"""S04-R1 decisions 5 and 6: sections by heading, the 4 scanner rules, packing, the header.

Fixtures are real corpus files, copied byte-exact at the locked SHAs (CC BY 4.0 / Apache-2.0):
- website_s04/pod-security-admission/1.30.md: the page's bytes from 1.30 to 1.37 (`cmp` with
  release 1.37, website 256a1f49).
- website_s04/authorization/excerpt-1.37.md: authorization.md lines 204-339 (website 256a1f49).
- website_s04/authentication/excerpt-1.32.md: authentication.md lines 332-499 (website a6b9d383).
- kubernetes/CHANGELOG-1.22-excerpt.md: CHANGELOG/CHANGELOG-1.22.md lines 3082-3193 (kubernetes
  7c596ad7).
- website_s05/feature-gates/<gate>/1.N.md: the gate's file at release 1.N (S05-T3).
- kep_old/0014-dynamic-audit-configuration-excerpt-1.20.md: an old single-file KEP, lines 1-61
  (enhancements 2df83383, S05-T4).
- sig_release/versioning/1.37.md: release-engineering/reference/versioning.md (sig-release
  9ad626fd, S05-T4).
- kubernetes/CHANGELOG-1.37-excerpt.md: CHANGELOG/CHANGELOG-1.37.md lines 1-250, the generated
  TOC and the whole v1.37.1 section (kubernetes 7c596ad7, S05-T6).
- kubernetes/CHANGELOG-1.22-beta.1-excerpt.md: CHANGELOG/CHANGELOG-1.22.md lines 3019-3303, the
  whole v1.22.0-beta.1 section (its stray fence at excerpt line 67), then v1.22.0-beta.0's
  downloads (kubernetes 7c596ad7, S05-T6).
- website_s04/rbac/table-excerpt-1.37.md: rbac.md lines 645-698, an HTML table with 3 blank lines
  inside its cells (website 256a1f49, S05-T7).
- kep_4317/README-excerpt-head.md: keps/sig-auth/4317-pod-certificates/README.md lines 901-994,
  with the comment block of lines 932-992 (enhancements 4be81e27, S05-T7).
- blog/kubernetes-configuration-best-practices/5b9bb69f.md: the post's whole file as website
  commit 5b9bb69f left it; 4 headings have a tab after their `###` (S05-T7).
- kubernetes/CHANGELOG-1.27-excerpt.md: CHANGELOG/CHANGELOG-1.27.md lines 2450-2466, part of a
  list that opens with an indented continuation line (kubernetes 7c596ad7, S05-T7).
- website_s05/feature-gates-page/excerpt-1.28.md: feature-gates.md lines 52-63, the start of the
  first table (website 6b57c309, release-1.28, S05-T7).

Expected values were read from the files by hand (line numbers below are the fixture's own,
1-based), never computed by the chunker.
"""

import re
from pathlib import Path

from orgknow.ingestion.chunker import (
    Block,
    Heading,
    changelog_title,
    chunk_markdown,
    chunk_text,
    chunk_version,
    governance_title,
    scan,
    split_sections,
)
from orgknow.ingestion.normalize import decode, split_front_matter

FIXTURES = Path(__file__).parents[1] / "fixtures"
PSA_FILE = FIXTURES / "website_s04" / "pod-security-admission" / "1.30.md"
PSA = "web:/docs/concepts/security/pod-security-admission/"
MAX_TOKENS = 512  # S04-R1 decision 5; 512 tokens = 2,048 characters (chars / 4)


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


def _psa_raw() -> bytes:
    return PSA_FILE.read_bytes()


def _psa_body_lines() -> list[str]:
    _, body = split_front_matter(decode(_psa_raw()))
    return body.split("\n")


def _paths(lines: list[str]) -> list[tuple[str, ...]]:
    return [section.heading_path for section in split_sections(lines)]


# --- Headings and code blocks (scanner rules 1-4) ---------------------------------------------


def test_pod_security_admission_has_a_preamble_and_seven_headed_sections() -> None:
    # The file's headings are lines 26, 33, 42, 80, 90, 128 and 139. Lines 64-74 sit inside a
    # ```yaml fence (63-76); 7 of its 9 `#` lines would match rule 1 without the fence.
    assert _paths(_psa_body_lines()) == [
        (),
        ("Built-in Pod Security admission enforcement",),
        ("Pod Security levels",),
        ("Pod Security Admission labels for namespaces",),
        ("Workload resources and Pod templates",),
        ("Exemptions",),
        ("Metrics",),
        ('{{% heading "whatsnext" %}}',),  # a shortcode heading stays as written
    ]


def test_the_yaml_fence_with_hash_comments_sits_whole_in_one_chunk() -> None:
    yaml_block = "\n".join(_lines(PSA_FILE)[62:76])  # file lines 63-76

    chunks = chunk_version(PSA, "docs_page", {"title": "Pod Security Admission"}, _psa_raw(), 512)

    holding = [c for c in chunks if yaml_block in c.text]
    assert len(holding) == 1
    assert holding[0].heading_path == ["Pod Security Admission labels for namespaces"]


def test_a_hash_line_inside_a_hugo_highlight_block_is_not_a_heading() -> None:
    # Line 6, `# DO NOT USE THE CONFIG AS IS. THIS IS AN EXAMPLE.`, is inside the
    # `{{< highlight yaml … >}}` block of lines 3-115. Headings: lines 1 and 125.
    lines = _lines(FIXTURES / "website_s04" / "authorization" / "excerpt-1.37.md")

    assert _paths(lines) == [
        ("Example configuration",),  # line 1 ends with ` {#authz-config-example}` (S05-T7)
        ("Authorization configuration and reloads",),
    ]


def test_headings_after_a_stray_indented_fence_are_found() -> None:
    # Line 4 is a "  ```" with no closing fence anywhere after it. Rule 3 closes it at line 23,
    # the next list item ("- Add DataSourceRef…", indent 0 < 2). Headings: lines 1, 49, 109.
    lines = _lines(FIXTURES / "kubernetes" / "CHANGELOG-1.22-excerpt.md")

    assert _paths(lines) == [("API Change",), ("Feature",), ("Documentation",)]


def test_an_indented_fence_in_a_list_item_closes_on_its_indented_closing_line() -> None:
    lines = [
        "1. Save this file:",  # 0
        "",
        "   ```yaml",  # 2: opened with indent 3
        "   kind: Pod",
        "",  # a blank line inside the fence doesn't end it
        "   metadata: {}",
        "   ```",  # 6: closes it (rule 2), although indented
        "",
        "   Then apply it.",  # 8: indent 3, so rule 3 doesn't apply; it's text, not code
        "2. Next step",
    ]

    assert scan(lines) == [Block(0, 1), Block(2, 7), Block(8, 10)]


# --- Packing: code blocks and tables are never cut (done when) --------------------------------


def test_an_oversize_code_block_is_exactly_one_chunk() -> None:
    # Lines 46-156: a ```yaml block of 6,341 characters, about 1,585 tokens (> 512).
    lines = _lines(FIXTURES / "website_s04" / "authentication" / "excerpt-1.32.md")
    code_block = "\n".join(lines[45:156])

    chunks = chunk_markdown("\n".join(lines), MAX_TOKENS)

    assert [
        body for _, body in chunks if "# CAUTION: this is an example configuration." in body
    ] == [code_block]
    # Line 1 ends with ` {#using-authentication-configuration}`, which is dropped (S05-T7).
    heading = ("Authentication configuration from a file",)
    assert {path for path, _ in chunks} == {heading}  # its `#` lines are not headings either


def test_a_table_within_the_limit_is_never_cut() -> None:
    # 1,200 + 2 (blank line) + 1,031 = 2,233 characters > 2,048: the table starts a new chunk,
    # whole, although 846 more characters would fit next to the first paragraph.
    paragraph = "a" * 1200
    rows = [f"| {i:02d} | {'v' * 90} |" for i in range(10)]  # 99 characters each
    table = "\n".join(["| Key | Value |", "|-----|-------|", *rows])  # 15 + 15 + 990 + 11 = 1,031
    after = "b" * 400
    body = f"## Modes\n\n{paragraph}\n\n{table}\n\n{after}\n"

    chunks = chunk_markdown(body, MAX_TOKENS)

    assert chunks == [(("Modes",), paragraph), (("Modes",), f"{table}\n\n{after}")]


def test_a_long_section_splits_at_a_paragraph_boundary() -> None:
    # 1,023 + 2 + 1,023 = 2,048 characters = 512 tokens: the first two paragraphs fit exactly.
    # The third makes 2,060 (515 tokens), so it starts the next chunk.
    first, second, third = "a" * 1023, "b" * 1023, "c" * 10
    body = f"# Title\n\n{first}\n\n{second}\n\n{third}\n"

    chunks = chunk_markdown(body, MAX_TOKENS)

    assert chunks == [(("Title",), f"{first}\n\n{second}"), (("Title",), third)]


# --- Chunk text -------------------------------------------------------------------------------


def test_the_header_of_a_docs_chunk() -> None:
    text = chunk_text("docs_page", "Pod Security Admission", PSA, ["Exemptions"], "Body text.")

    assert text == (
        "Source: docs_page\n"
        "Title: Pod Security Admission\n"
        "Document: web:/docs/concepts/security/pod-security-admission/\n"
        "Section: Exemptions\n"
        "\n"
        "Body text."
    )


def test_the_header_omits_the_section_before_the_first_heading() -> None:
    assert chunk_text("docs_page", "T", "web:/t/", [], "Intro.") == (
        "Source: docs_page\nTitle: T\nDocument: web:/t/\n\nIntro."
    )


def test_a_kep_chunk_from_its_readme() -> None:
    readme = b"# KEP-2579: PSP Replacement Policy\n\n## Design Details\n\n### Updates\n\nText.\n"

    chunks = chunk_version("kep:2579", "kep", {"title": "PSP Replacement Policy"}, readme, 512)

    # The two outer headings have no text of their own, so they make no chunk (no merging).
    assert [(c.ordinal, c.heading_path, c.text) for c in chunks] == [
        (
            0,
            ["KEP-2579: PSP Replacement Policy", "Design Details", "Updates"],
            "Source: kep\n"
            "Title: KEP-2579: PSP Replacement Policy\n"
            "Document: kep:2579\n"
            "Section: KEP-2579: PSP Replacement Policy > Design Details > Updates\n"
            "\n"
            "Text.",
        )
    ]


def test_the_body_is_raw_markdown_without_front_matter_and_with_lf() -> None:
    raw = b"---\ntitle: T\nreviewers:\n- alice\n---\n\nSee [docs](/docs/x/)  {{< note >}}\n"

    chunks = chunk_version("web:/t/", "docs_page", {"title": "T"}, raw, 512)
    crlf = chunk_version("web:/t/", "docs_page", {"title": "T"}, raw.replace(b"\n", b"\r\n"), 512)

    # Link targets, double spaces and shortcodes stay: this is not the normalized text.
    assert [c.text for c in chunks] == [
        "Source: docs_page\nTitle: T\nDocument: web:/t/\n\nSee [docs](/docs/x/)  {{< note >}}"
    ]
    assert crlf == chunks


def test_chunking_the_same_input_twice_gives_identical_texts() -> None:
    first = chunk_version(PSA, "docs_page", {"title": "Pod Security Admission"}, _psa_raw(), 512)
    second = chunk_version(PSA, "docs_page", {"title": "Pod Security Admission"}, _psa_raw(), 512)

    assert len(first) > 1
    assert [c.text for c in first] == [c.text for c in second]


# --- A gate's stages in its chunk text (S05-R1 decision 1) ------------------------------------

GATES = FIXTURES / "website_s05" / "feature-gates"


def test_a_gate_chunk_starts_with_its_stages_as_yaml() -> None:
    raw = (GATES / "StrictIPCIDRValidation" / "1.37.md").read_bytes()
    # The version's metadata as Postgres jsonb returns it: keys reordered (shortest first). The
    # YAML keeps the file's own order, so the stored text doesn't depend on that.
    metadata = {
        "title": "StrictIPCIDRValidation",
        "stages": [
            {"stage": "alpha", "toVersion": "1.35", "fromVersion": "1.33", "defaultValue": False},
            {"stage": "beta", "fromVersion": "1.36", "defaultValue": True},
        ],
    }

    chunks = chunk_version(
        "gate:StrictIPCIDRValidation", "feature_gate_reference", metadata, raw, 512
    )

    # The pinned chunk text, typed by hand from the fixture: header, YAML, body.
    assert [(c.ordinal, c.heading_path, c.text) for c in chunks] == [
        (
            0,
            [],
            "Source: feature_gate_reference\n"
            "Title: StrictIPCIDRValidation\n"
            "Document: gate:StrictIPCIDRValidation\n"
            "\n"
            "stages:\n"
            "- stage: alpha\n"
            "  defaultValue: false\n"
            "  fromVersion: '1.33'\n"
            "  toVersion: '1.35'\n"
            "- stage: beta\n"
            "  defaultValue: true\n"
            "  fromVersion: '1.36'\n"
            "\n"
            "Use stricter validation for fields containing IP addresses and CIDR values.\n"
            "\n"
            "In particular, with this feature gate enabled, octets within IPv4 addresses are\n"
            "not allowed to have any leading `0`s, and IPv4-mapped IPv6 values (e.g.\n"
            "`::ffff:192.168.0.1`) are forbidden. These sorts of values can potentially cause\n"
            "security problems when different components interpret the same string as\n"
            "referring to different IP addresses (as in CVE-2021-29923).\n"
            "\n"
            "This tightening applies only to fields in build-in API kinds, and not to\n"
            "custom resource kinds, values in Kubernetes configuration files, or\n"
            "command-line arguments.",
        )
    ]


def test_removed_follows_the_stages_and_one_blank_line_precedes_the_body() -> None:
    # Hand-written after PodHasNetworkCondition at 1.37, which has `removed: true` after its
    # stages, with a body that starts with a blank line, as 34 of the 864 distinct real gate
    # files (1.29-1.37) do.
    # The text still has exactly one blank line between the YAML and the body.
    raw = (
        b"---\ntitle: PodHasNetworkCondition\ncontent_type: feature_gate\n_build:\n"
        b"  list: never\n  render: false\n\nstages:\n  - stage: alpha \n"
        b'    defaultValue: false\n    fromVersion: "1.25"\n    toVersion: "1.27"\n\n'
        b"removed: true\n---\n\nEnable the kubelet to mark the PodHasNetwork condition.\n"
    )
    metadata = {"title": "PodHasNetworkCondition", "stages": [], "removed": True}

    (chunk,) = chunk_version(
        "gate:PodHasNetworkCondition", "feature_gate_reference", metadata, raw, 512
    )

    assert chunk.text == (
        "Source: feature_gate_reference\n"
        "Title: PodHasNetworkCondition\n"
        "Document: gate:PodHasNetworkCondition\n"
        "\n"
        "stages:\n"
        "- stage: alpha\n"
        "  defaultValue: false\n"
        "  fromVersion: '1.25'\n"
        "  toVersion: '1.27'\n"
        "removed: true\n"
        "\n"
        "Enable the kubelet to mark the PodHasNetwork condition."
    )


def test_stage_values_are_kept_as_yaml_reads_them() -> None:
    # The real 1.32 file writes `- stage: alpha ` with a trailing space. In YAML, trailing spaces
    # after a plain value aren't part of it, so the value is `alpha`; a quoted value keeps its
    # spaces. Nothing is trimmed or mapped on top of what YAML reads.
    real = (GATES / "APIServingWithRoute" / "1.32.md").read_bytes()
    assert b"  - stage: alpha \n" in real
    quoted = real.replace(b"  - stage: alpha \n", b"  - stage: 'alpha '\n")
    metadata = {"title": "APIServingWithRoute"}

    (plain,) = chunk_version(
        "gate:APIServingWithRoute", "feature_gate_reference", metadata, real, 512
    )
    (spaced,) = chunk_version(
        "gate:APIServingWithRoute", "feature_gate_reference", metadata, quoted, 512
    )

    assert "\n\nstages:\n- stage: alpha\n  defaultValue: false\n" in plain.text
    assert "\n\nstages:\n- stage: 'alpha '\n  defaultValue: false\n" in spaced.text


def test_only_a_gate_document_with_stages_gets_the_yaml() -> None:
    page = b"---\ntitle: Feature Gates\nstages:\n  - stage: alpha\n---\nThe gates.\n"
    no_stages = b"---\ntitle: SomeGate\ncontent_type: feature_gate\n---\nA gate.\n"

    # The feature-gates page is a `web:` document; a gate file without `stages` has nothing to add.
    (web,) = chunk_version(
        "web:/docs/gates/", "feature_gate_reference", {"title": "Feature Gates"}, page, 512
    )
    (bare,) = chunk_version(
        "gate:SomeGate", "feature_gate_reference", {"title": "SomeGate"}, no_stages, 512
    )

    assert web.text.endswith("Document: web:/docs/gates/\n\nThe gates.")
    assert bare.text.endswith("Document: gate:SomeGate\n\nA gate.")


# --- Old single-file KEPs and governance docs (S05-T4) -----------------------------------------

OLD_KEP = "kep:sig-auth/0014-dynamic-audit-configuration"
OLD_KEP_FILE = FIXTURES / "kep_old" / "0014-dynamic-audit-configuration-excerpt-1.20.md"


def test_an_old_single_file_kep_is_chunked_without_front_matter_or_kep_prefix() -> None:
    raw = OLD_KEP_FILE.read_bytes()

    chunks = chunk_version(OLD_KEP, "kep", {"title": "Dynamic Audit Configuration"}, raw, 512)

    # Headings at fixture lines 23 (#), 25 (##) and 57 (##); the table of contents (27-55) is
    # the text of "Table of Contents". The title is the front matter's, with no `KEP-<n>:`.
    assert [c.heading_path for c in chunks] == [
        ["Dynamic Audit Control", "Table of Contents"],
        ["Dynamic Audit Control", "Summary"],
    ]
    # Lines 27 `<!-- toc -->` and 55 `<!-- /toc -->` are one-line comment blocks: dropped (rule 6,
    # S05-T7). The visible table of contents between them, lines 28-54, stays.
    assert chunks[0].text == (
        "Source: kep\n"
        "Title: Dynamic Audit Configuration\n"
        "Document: kep:sig-auth/0014-dynamic-audit-configuration\n"
        "Section: Dynamic Audit Control > Table of Contents\n"
        "\n" + "\n".join(_lines(OLD_KEP_FILE)[27:54])
    )
    assert all("status: implementable" not in c.text for c in chunks)


def test_a_governance_doc_is_chunked_whole_under_its_metadata_title() -> None:
    raw = b"# Release Engineering\n\nIntro.\n\n## Handbooks\n\nBranch creation.\n"
    metadata = {"title": "Release Engineering"}

    chunks = chunk_version(
        "sig-release:release-engineering/README.md", "governance_doc", metadata, raw, 512
    )

    assert [c.text for c in chunks] == [
        "Source: governance_doc\nTitle: Release Engineering\n"
        "Document: sig-release:release-engineering/README.md\n"
        "Section: Release Engineering\n\nIntro.",
        "Source: governance_doc\nTitle: Release Engineering\n"
        "Document: sig-release:release-engineering/README.md\n"
        "Section: Release Engineering > Handbooks\n\nBranch creation.",
    ]


VERSIONING = "release-engineering/reference/versioning.md"


def test_a_governance_title_is_the_first_h1_heading() -> None:
    text = (FIXTURES / "sig_release" / "versioning" / "1.37.md").read_text(encoding="utf-8")

    # Line 1 of the real file (S05-R2 decision 4).
    assert governance_title(text, VERSIONING) == "Kubernetes Release Versioning"


def test_a_governance_title_drops_html_comments() -> None:
    # Line 1 of release-engineering/reference/gcp.md at the sig-release 1.37 snapshot.
    text = "# Google Cloud Platform <!-- omit in toc -->\n\n- [IAM](#iam)\n"

    assert governance_title(text, "release-engineering/reference/gcp.md") == "Google Cloud Platform"


def test_a_governance_doc_without_an_h1_heading_is_titled_by_its_path() -> None:
    # A `#` line inside a code block is no heading (scanner rule 1); `##` is not an H1.
    text = "Moved to the reference folder.\n\n```\n# not a heading\n```\n\n## Details\n"

    assert governance_title(text, "release-engineering/platforms/guide.md") == (
        "release-engineering/platforms/guide.md"
    )


# --- CHANGELOGs: release notes only (S05-T6, S05-R2 decisions 4 and 8) -----------------------

SHA512 = re.compile(r"[0-9a-f]{128}")  # a row of a download table (the demo query's pattern)
CHANGES = ("Changes by Kind",)
DEPENDENCIES = ("Dependencies",)


def test_a_changelog_title_is_its_file_name() -> None:
    assert changelog_title(37) == "CHANGELOG-1.37"


def test_changelog_chunks_leave_out_the_toc_and_the_download_tables() -> None:
    raw = (FIXTURES / "kubernetes" / "CHANGELOG-1.37-excerpt.md").read_bytes()
    assert len(SHA512.findall(raw.decode())) == 22  # the input has them (grep -c, by hand)

    chunks = chunk_version(
        "changelog:1.37", "release_record", {"title": "CHANGELOG-1.37"}, raw, 512
    )

    # Lines 1-155 are the generated TOC (before the first heading, line 157): no chunk. Lines
    # 160-220 are `## Downloads for v1.37.1` and its 5 tables: no chunk. `# v1.37.1`, `## Changelog
    # since v1.37.0`, `## Changes by Kind` and `## Dependencies` have no text of their own.
    assert [tuple(c.heading_path) for c in chunks] == [
        ("v1.37.1", *CHANGES, "Feature"),  # line 227
        ("v1.37.1", *CHANGES, "Failing Test"),  # line 231
        ("v1.37.1", *CHANGES, "Bug or Regression"),  # lines 235-239
        ("v1.37.1", *DEPENDENCIES, "Added"),  # line 244
        ("v1.37.1", *DEPENDENCIES, "Changed"),  # line 247
        ("v1.37.1", *DEPENDENCIES, "Removed"),  # line 250
    ]
    assert [c.ordinal for c in chunks] == [0, 1, 2, 3, 4, 5]
    assert chunks[0].text == (
        "Source: release_record\nTitle: CHANGELOG-1.37\nDocument: changelog:1.37\n"
        "Section: v1.37.1 > Changes by Kind > Feature\n\n"
        + _lines(FIXTURES / "kubernetes" / "CHANGELOG-1.37-excerpt.md")[226]
    )
    assert not any(SHA512.search(c.text) or "GENERATED_TOC" in c.text for c in chunks)


def test_download_tables_after_a_stray_fence_are_left_out_too() -> None:
    raw = (FIXTURES / "kubernetes" / "CHANGELOG-1.22-beta.1-excerpt.md").read_bytes()
    assert len(SHA512.findall(raw.decode())) == 46  # both sections' tables (grep -c, by hand)

    chunks = chunk_version(
        "changelog:1.22", "release_record", {"title": "CHANGELOG-1.22"}, raw, 512
    )

    # The stray "  ```" at line 67 (in API Change) closes at the next list item (rule 3), so
    # `# v1.22.0-beta.0` (line 239) is still a heading and its downloads (242-285) are left out.
    # A long section packs into several chunks; each heading path is listed once, in order.
    beta_1 = "v1.22.0-beta.1"
    assert list(dict.fromkeys(tuple(c.heading_path) for c in chunks)) == [
        (beta_1, "Urgent Upgrade Notes", "(No, really, you MUST read this before you upgrade)"),
        (beta_1, *CHANGES, "Deprecation"),
        (beta_1, *CHANGES, "API Change"),
        (beta_1, *CHANGES, "Feature"),
        (beta_1, *CHANGES, "Documentation"),
        (beta_1, *CHANGES, "Bug or Regression"),
        (beta_1, *CHANGES, "Other (Cleanup or Flake)"),
        (beta_1, *DEPENDENCIES, "Added"),
        (beta_1, *DEPENDENCIES, "Changed"),
        (beta_1, *DEPENDENCIES, "Removed"),
    ]
    assert not any(SHA512.search(c.text) or "Downloads for" in c.text for c in chunks)


# --- Heading text: anchors, inline comments, tabs (S05-T7) -------------------------------------


def test_a_heading_loses_its_anchor_and_inline_comments() -> None:
    lines = [
        "## Example configuration {#authz-config-example}",  # authorization.md, a spaced anchor
        "Text.",
        # Line 42 of the Gateway API v1.2 post (website 022282e5): no space before the anchor.
        "### Change to `.status.supportedFeatures` (experimental){#status-supported-features}",
        "Text.",
        "# Branch Manager Handbook <!-- omit in toc -->",  # a sig-release heading
        "Text.",
        "## Both {#both} <!-- omit in toc -->",
        "Text.",
        "## Not at the end {#kept} of the line",
        "Text.",
    ]

    assert _paths(lines) == [
        ("Example configuration",),
        ("Example configuration", "Change to `.status.supportedFeatures` (experimental)"),
        ("Branch Manager Handbook",),
        ("Branch Manager Handbook", "Both"),
        ("Branch Manager Handbook", "Not at the end {#kept} of the line"),
    ]


def test_a_governance_title_drops_the_anchor_too() -> None:
    text = "# Release Team Handbook {#handbook} <!-- omit in toc -->\n\nText.\n"

    assert governance_title(text, "release-team/README.md") == "Release Team Handbook"


BEST_PRACTICES = FIXTURES / "blog" / "kubernetes-configuration-best-practices" / "5b9bb69f.md"


def test_a_tab_after_the_hashes_makes_a_heading() -> None:
    _, body = split_front_matter(decode(BEST_PRACTICES.read_bytes()))

    headings = [(h.level, h.text) for h in scan(body.split("\n")) if isinstance(h, Heading)]

    # `grep -n '^#'` on the file: 25 lines. File line 180 is inside a ```bash block, so 24
    # headings; lines 40, 43, 54 and 158 have a tab after `###` (marked "tab").
    assert headings == [
        (2, "General configuration practices"),
        (3, "Use the latest stable API version"),
        (3, "Store configuration in version control"),
        (3, "Write configs in YAML not JSON"),
        (3, "Keep configuration simple and minimal"),  # tab
        (3, "Group related objects together"),  # tab
        (3, "Add helpful annotations"),  # tab
        (2, "Managing Workloads: Pods, Deployments, and Jobs"),
        (3, "Use Deployments for apps that should always be running"),
        (3, "Use Jobs for tasks that should finish"),
        (2, "Service Configuration and Networking"),
        (3, "Create Services before workloads that use them"),
        (3, "Use DNS for Service discovery"),
        (3, "Avoid `hostPort` and `hostNetwork` unless absolutely necessary"),
        (3, "Use headless Services for internal discovery"),
        (2, "Working with labels effectively"),
        (3, "Use semantics labels"),
        (3, "Use common Kubernetes labels"),
        (3, "Manipulate labels for debugging"),  # tab
        (2, "Handy kubectl tips"),
        (3, "Apply entire directories"),
        (3, "Use label selectors to get or delete resources"),
        (3, "Quickly create Deployments and Services"),
        (2, "Conclusion"),
    ]


# --- Rule 5: an HTML table is one block (S05-T7) -----------------------------------------------

RBAC_TABLE = FIXTURES / "website_s04" / "rbac" / "table-excerpt-1.37.md"


def test_an_html_table_with_blank_lines_in_its_cells_is_one_block() -> None:
    # 54 lines, `<table>` to `</table>`; lines 22, 34 and 47 are blank (inside <td> cells).
    lines = _lines(RBAC_TABLE)[:54]  # the file ends with a newline: drop the empty last item

    assert scan(lines) == [Block(0, 54)]
    # 2,264 characters (566 tokens) > 512: still one chunk, the whole table.
    assert chunk_markdown("## User-facing roles\n\n" + "\n".join(lines), MAX_TOKENS) == [
        (("User-facing roles",), "\n".join(lines))
    ]


def test_an_html_table_opener_ends_a_paragraph_and_runs_to_its_closing_line() -> None:
    lines = [
        "Text before.",  # 0
        "  <TABLE class=x>",  # 1: up to 3 spaces, any case; ends the paragraph
        "<tr><td>a",
        "",
        "# not a heading</td></tr>",  # 4: inside the table
        "</table> trailing",  # 5: the first line containing </table>
        "After.",  # 6
        "<table><tr><td>one line</td></tr></table>",  # 7: opens and closes on one line
        "",
        "<table>",  # 9: never closed: runs to the end of the body
        "",
        "# not a heading either",
    ]

    assert scan(lines) == [Block(0, 1), Block(1, 6), Block(6, 7), Block(7, 8), Block(9, 12)]


# --- Rule 6: HTML comment blocks are dropped (S05-T7) ------------------------------------------

KEP_4317 = FIXTURES / "kep_4317" / "README-excerpt-head.md"


def test_a_kep_template_comment_makes_no_section_and_no_text() -> None:
    raw = KEP_4317.read_bytes()

    chunks = chunk_version("kep:4317", "kep", {"title": "Pod Certificates"}, raw, MAX_TOKENS)

    # Line 1 is `### Graduation Criteria`, lines 3-30 its text. Lines 32-92 are a comment block
    # holding `#### Alpha` (59), `#### Beta` (64), `#### GA` (70) and `#### Deprecation` (86): no
    # section. Line 94, `### Upgrade / Downgrade Strategy`, has no text: no chunk.
    assert [(c.heading_path, c.text) for c in chunks] == [
        (
            ["Graduation Criteria"],
            "Source: kep\nTitle: KEP-4317: Pod Certificates\nDocument: kep:4317\n"
            "Section: Graduation Criteria\n\n" + "\n".join(_lines(KEP_4317)[2:30]),
        )
    ]
    assert not any("<!--" in c.text or "Define graduation milestones" in c.text for c in chunks)


def test_comment_blocks_drop_whole_lines_and_keep_the_blank_lines_around_them() -> None:
    lines = [
        "# Title",  # 0
        "Text one.",  # 1
        "<!-- a comment opener ends a paragraph -->",  # 2: one line, dropped
        "Text two.",  # 3
        "",  # 4
        "  <!--",  # 5: up to 3 spaces
        "# not a heading",  # 6
        "",  # 7: a blank line inside the comment goes with it
        "--> text after the closing marker is dropped too",  # 8
        "",  # 9
        "Inline <!-- kept --> in a paragraph line.",  # 10
        "```html",  # 11
        "<!-- inside a code block: kept -->",  # 12
        "```",  # 13
        "<!-- never closed: runs to the end of the body",  # 14
        "## not a heading either",  # 15
    ]

    # Lines 4 and 9 (blank, outside the comment) stay; lines 2 and 5-8 don't.

    assert chunk_markdown("\n".join(lines), MAX_TOKENS) == [
        (
            ("Title",),
            "Text one.\n"
            "Text two.\n"
            "\n"
            "\n"
            "Inline <!-- kept --> in a paragraph line.\n"
            "```html\n"
            "<!-- inside a code block: kept -->\n"
            "```",
        )
    ]


# --- Decision 1: oversize lists and pipe tables are cut (S05-T7) -------------------------------

CHANGELOG_27 = FIXTURES / "kubernetes" / "CHANGELOG-1.27-excerpt.md"


def test_an_oversize_list_is_cut_between_items() -> None:
    lines = _lines(CHANGELOG_27)[:17]  # one paragraph block: no blank line

    # Line lengths (awk): 105 103 95 181 | 351 | 248 | 231 | 322 | 210 | 196 | 295 | 156 80 308 |
    # 114 194 | 148. Lines 1-4 continue the item before the excerpt; lines 13-14 are nested items
    # of line 12, and line 16 continues line 15. 3,353 characters in all (839 tokens).
    # Up to 200 tokens (800 characters), packed greedily by hand:
    # 1-4 (487; + line 5 would be 839) | 5-6 (600) | 7-9 (765) | 10-11 (492) | 12-14 (546) | 15-17.
    def text(first: int, last: int) -> str:  # fixture lines, 1-based, inclusive
        return "\n".join(lines[first - 1 : last])

    chunks = chunk_markdown("\n".join(lines), 200)

    assert [body for _, body in chunks] == [
        text(1, 4),
        text(5, 6),
        text(7, 9),
        text(10, 11),
        text(12, 14),
        text(15, 17),
    ]


def test_list_cut_points_are_items_at_the_smallest_indent() -> None:
    # The contract's pinned format, plus `2)`, a `---` line and an item longer than the limit.
    lines = [
        "  continuation of the previous item",
        "- Item A",
        "  more text of A",
        "  - nested item of A",
        "- Item B",
        "1. Item C (numbered lists alike)",
        "---",
        "2) Item D, longer than the limit on its own",
    ]

    # Up to 5 tokens (20 characters): every piece is a chunk of its own; none is cut further.
    assert [body for _, body in chunk_markdown("\n".join(lines), 5)] == [
        "  continuation of the previous item",
        "- Item A\n  more text of A\n  - nested item of A",
        "- Item B",
        "1. Item C (numbered lists alike)\n---",
        "2) Item D, longer than the limit on its own",
    ]


def test_a_code_block_or_a_list_within_the_limit_is_not_cut() -> None:
    code = "```yaml\n- a: 1\n- b: 2\n- c: 3\n```"  # 32 characters (8 tokens), list-like lines
    short_list = "- one\n- two"  # 11 characters (3 tokens)

    assert chunk_markdown(f"{code}\n\n{short_list}", 7) == [((), code), ((), short_list)]


FEATURE_GATES_28 = FIXTURES / "website_s05" / "feature-gates-page" / "excerpt-1.28.md"


def test_an_oversize_pipe_table_is_cut_between_rows_with_its_header_repeated() -> None:
    body = FEATURE_GATES_28.read_text(encoding="utf-8")
    # Line lengths (awk): 44, 0, 90 (the table shortcode), 0, then the table: 45 45 51 45 60 53
    # 59 53 (418 characters with newlines, 105 tokens). Up to 55 tokens (220 characters), by hand:
    # shortcode + blank + header, delimiter, first row = 235 > 220, so the shortcode is alone;
    # 45+45+51+45 (+3) = 189, + row 60 = 250 > 220; header (91) + 60 + 53 (+2) = 206, + row 59 =
    # 266 > 220; header + 59 + 53 (+2) = 205.
    header = (
        "| Feature | Default | Stage | Since | Until |\n"
        "|---------|---------|-------|-------|-------|"
    )
    section = ("Feature gates for Alpha or Beta features",)

    chunks = chunk_markdown(body, 55)

    assert chunks == [
        (
            section,
            '{{< table caption="Feature gates for features in Alpha or Beta states" '
            'sortable="true" >}}',
        ),
        (
            section,
            f"{header}\n"
            "| `APIListChunking` | `false` | Alpha | 1.8 | 1.8 |\n"
            "| `APIListChunking` | `true` | Beta | 1.9 | |",
        ),
        (
            section,
            f"{header}\n"
            "| `APIPriorityAndFairness` | `false` | Alpha | 1.18 | 1.19 |\n"
            "| `APIPriorityAndFairness` | `true` | Beta | 1.20 | |",
        ),
        (
            section,
            f"{header}\n"
            "| `APIResponseCompression` | `false` | Alpha | 1.7 | 1.15 |\n"
            "| `APIResponseCompression` | `true` | Beta | 1.16 | |",
        ),
    ]


# --- Decision 4: no "Downloads for" section in any source (S05-T7) ----------------------------


def test_a_docs_page_drops_downloads_sections_but_keeps_its_text_before_the_first_heading() -> None:
    # The shape of the 1.20 release notes page (web:/docs/setup/release/notes/), shortened.
    raw = (
        b"---\ntitle: v1.20 Release Notes\n---\n\nBefore any heading.\n\n# v1.20.0\n\nIntro.\n\n"
        b"## Downloads for v1.20.0\n\n### Source Code\n\nfilename | sha512 hash\n-------- | ---\n"
        b"[kubernetes.tar.gz](https://dl.k8s.io/v1.20.0/kubernetes.tar.gz) | `"
        + b"a"
        * 128
        + b"`\n"
        b"\n## Changelog since v1.19.0\n\nNotes.\n"
    )

    chunks = chunk_version(
        "web:/docs/setup/release/notes/",
        "release_record",
        {"title": "v1.20 Release Notes"},
        raw,
        512,
    )

    # The table-of-contents rule stays CHANGELOG-only: the text before `# v1.20.0` is kept.
    assert [(c.heading_path, c.text.split("\n\n", 1)[1]) for c in chunks] == [
        ([], "Before any heading."),
        (["v1.20.0"], "Intro."),
        (["v1.20.0", "Changelog since v1.19.0"], "Notes."),
    ]
