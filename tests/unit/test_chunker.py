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

Expected values were read from the files by hand (line numbers below are the fixture's own,
1-based), never computed by the chunker.
"""

from pathlib import Path

from orgknow.ingestion.chunker import (
    Block,
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
        ("Example configuration {#authz-config-example}",),
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
    heading = ("Authentication configuration from a file {#using-authentication-configuration}",)
    assert {path for path, _ in chunks} == {heading}  # its `#` lines are not headings either


def test_a_table_is_never_cut() -> None:
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


def test_an_old_single_file_kep_is_chunked_without_front_matter_or_kep_prefix() -> None:
    raw = (FIXTURES / "kep_old" / "0014-dynamic-audit-configuration-excerpt-1.20.md").read_bytes()

    chunks = chunk_version(OLD_KEP, "kep", {"title": "Dynamic Audit Configuration"}, raw, 512)

    # Headings at fixture lines 23 (#), 25 (##) and 57 (##); the table of contents (27-55) is
    # the text of "Table of Contents". The title is the front matter's, with no `KEP-<n>:`.
    assert [c.heading_path for c in chunks] == [
        ["Dynamic Audit Control", "Table of Contents"],
        ["Dynamic Audit Control", "Summary"],
    ]
    assert chunks[0].text.startswith(
        "Source: kep\n"
        "Title: Dynamic Audit Configuration\n"
        "Document: kep:sig-auth/0014-dynamic-audit-configuration\n"
        "Section: Dynamic Audit Control > Table of Contents\n"
        "\n"
        "<!-- toc -->\n"
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
