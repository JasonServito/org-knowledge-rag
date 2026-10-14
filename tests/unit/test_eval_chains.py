"""S13-T1: the chain label check's reading of the gold chains file (the S13-R1 contract, "Pinned:
T4", for the format). Only `texts` entries are labels to check; `not_public`, `not_stored` and
`none` steps cite no stored text. The database half is in tests/integration/test_ingest_github.py.
"""

from pathlib import Path

from orgknow.eval.chains import ChainLabel, label_line, text_labels

GOLD = """\
version: chains-test
chains:
  - seed: kep:1
    role: built-on
    question: "Why?"
    steps:
      - step: problem
        date: 2020-10-14
        texts:
          - document: "gh:sig-release/discussions/12"
            section: "Opening post · @erin · 2020-10-14"
          - {document: "kep:1", section: "KEP-1: X > Motivation"}
      - step: discussion
        not_public: "https://docs.google.com/document/d/x"
      - step: implementation
        date: 2021-08-04
        texts:
          - {document: "web:/blog/2021/07/20/x/"}
          - {document: "web:/blog/2021/08/04/y/", section: ""}
  - seed: kep:2
    role: held-out
    question: "Why not?"
    steps:
      - step: decision
        not_stored: "https://github.com/kubernetes/enhancements/pull/5140"
"""


def test_every_texts_entry_is_a_label_in_file_order(tmp_path: Path) -> None:
    path = tmp_path / "chains.yaml"
    path.write_text(GOLD, encoding="utf-8")

    assert text_labels(path) == [
        ChainLabel(
            seed="kep:1",
            step="problem",
            document="gh:sig-release/discussions/12",
            section="Opening post · @erin · 2020-10-14",
        ),
        ChainLabel(seed="kep:1", step="problem", document="kep:1", section="KEP-1: X > Motivation"),
        ChainLabel(seed="kep:1", step="implementation", document="web:/blog/2021/07/20/x/"),
        ChainLabel(
            seed="kep:1", step="implementation", document="web:/blog/2021/08/04/y/", section=""
        ),
    ]


def test_a_label_line_names_the_chain_step_document_and_section() -> None:
    label = ChainLabel(
        seed="kep:2572",
        step="decision",
        document="gh:enhancements/pull/2567",
        section="Comments > @dims · 2021-04-19",
    )

    assert label_line(label, 2) == (
        'kep:2572 decision  gh:enhancements/pull/2567  "Comments > @dims · 2021-04-19"  2 texts'
    )
    whole = ChainLabel(seed="kep:1", step="implementation", document="web:/blog/x/")
    assert label_line(whole, 0) == "kep:1 implementation  web:/blog/x/  (whole document)  0 texts"
