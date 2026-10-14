"""S13-T3: how `orgknow chain` prints a stored chain (the contract's "CLI output"), from a
hand-built chain: a header (seed, title, built time), then one line per step in step order: date,
step, source URL, the canonical id and section, tier, found_by and "via ...", or `missing:
<reason>`. Expected lines are typed by hand."""

from datetime import datetime

import pytest

from orgknow import cli
from orgknow.provenance.chain import Chain, ChainStep, chain_lines


def _cited(step: str, **fields: object) -> ChainStep:
    base: dict[str, object] = {
        "step": step,
        "occurred_at": datetime.fromisoformat("2021-04-23T15:38:03Z"),
        "chunk_id": 1,
        "canonical_id": "gh:enhancements/pull/2567",
        "heading_path": ["Comments", "@dchen1107 · 2021-04-22"],
        "source_type": "discussion",
        "source_url": "https://github.com/kubernetes/enhancements/pull/2567",
        "tier": 7,
        "found_by": "merge_event",
        "via_chunk_id": 2,
        "via_canonical_id": "gh:enhancements/issues/2572",
        "via_heading_path": [
            "Opening post · @justaugustus · 2021-03-15",
            "Enhancement Description",
        ],
        "missing_reason": None,
    }
    return ChainStep.model_validate(base | fields)


def _missing(step: str, reason: str) -> ChainStep:
    nothing = dict.fromkeys(ChainStep.model_fields)
    return ChainStep.model_validate(nothing | {"step": step, "missing_reason": reason})


def test_a_chain_prints_a_header_then_one_line_per_step() -> None:
    chain = Chain(
        seed="kep:2572",
        title="KEP-2572: Defining the Kubernetes Release Cadence",
        built_at=datetime.fromisoformat("2026-10-13T22:01:02.5+00:00"),
        steps=[
            _cited("decision"),
            _cited(
                "proposal",
                occurred_at=None,
                canonical_id="kep:2572",
                heading_path=["KEP-2572: Defining the Kubernetes Release Cadence", "Summary"],
                source_url="https://github.com/kubernetes/enhancements/blob/abc/README.md",
                tier=None,
                found_by="seed",
                via_chunk_id=None,
                via_canonical_id=None,
                via_heading_path=None,
            ),
            _missing("implementation", "no_linking_text"),
        ],
    )

    assert chain_lines(chain) == [
        "kep:2572: KEP-2572: Defining the Kubernetes Release Cadence "
        "(built 2026-10-13 22:01:02 UTC)",
        "2021-04-23  decision        https://github.com/kubernetes/enhancements/pull/2567  "
        "gh:enhancements/pull/2567 \u203a Comments > @dchen1107 · 2021-04-22  tier 7  "
        "merge_event via gh:enhancements/issues/2572 \u203a Opening post · @justaugustus · "
        "2021-03-15 > Enhancement Description",
        "----------  proposal        "
        "https://github.com/kubernetes/enhancements/blob/abc/README.md  "
        "kep:2572 \u203a KEP-2572: Defining the Kubernetes Release Cadence > Summary  no tier  "
        "seed",
        "----------  implementation  missing: no_linking_text",
    ]


def test_orgknow_chain_needs_a_canonical_id(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["chain"])

    assert exit_info.value.code == 2
    assert "orgknow chain: error" in capsys.readouterr().err
