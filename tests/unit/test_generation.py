"""The answer step (S04-T6): validator, fill-in, prompt, failure states, and `answer`.

Every expected value is typed by hand from the S04-R2 contract's pinned formats and from real rows
of the dev database (chunk 551, PSA "Exemptions", and chunk 4916, the KEP-2579 summary; checked
2026-10-06). None is computed by the code under test. No test calls a network.
"""

import json
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest
from tests.conftest import FakeGenerator

from orgknow.db.models import Hit
from orgknow.generation.generator import (
    AnthropicGenerator,
    GenerationError,
    answer,
    checked_output,
)
from orgknow.generation.prompt import SYSTEM_PROMPT, evidence_block
from orgknow.generation.schema import Generation, ModelAnswer, TokenUsage
from orgknow.generation.validate import fill_in, rejection_reason
from orgknow.settings import Settings

REAL_MANIFEST = Path(__file__).parents[2] / "config" / "corpus_manifest.yaml"
QUESTION = "What enforces pod security standards in-tree?"

PSA_SHA = "c28dcd8393562ddc6adf89b920ad3c396166a31b"
PSA_TEXT = (
    "Source: docs_page\n"
    "Title: Pod Security Admission\n"
    "Document: web:/docs/concepts/security/pod-security-admission/\n"
    "Section: Exemptions\n"
    "\n"
    "You can define _exemptions_ from pod security enforcement."
)
KEP_SHA = "0ffd37f8925d8a9af7ce7a7409007db8285a30b1"
KEP_TEXT = (
    "Source: kep\n"
    "Title: KEP-2579: PSP Replacement Policy\n"
    "Document: kep:2579\n"
    "Section: KEP-2579: Pod Security Admission Control > Summary\n"
    "\n"
    "Replace PodSecurityPolicy with a new built-in admission controller."
)


def _docs_hit(chunk_id: int = 551, **changes: Any) -> Hit:
    hit = Hit(
        chunk_id=chunk_id,
        content_hash="a" * 64,
        distance=0.25,
        text=PSA_TEXT,
        canonical_id="web:/docs/concepts/security/pod-security-admission/",
        source_type="docs_page",
        heading_path=["Exemptions"],
        release_windows=[(30, None)],
        claimed_status=None,
        claimed_stage=None,
        snapshot_repo="website",
        snapshot_sha=PSA_SHA,
        source_path="content/en/docs/concepts/security/pod-security-admission.md",
        metadata={"title": "Pod Security Admission"},
    )
    return hit.model_copy(update=changes)


def _kep_hit(**changes: Any) -> Hit:
    hit = Hit(
        chunk_id=4916,
        content_hash="b" * 64,
        distance=0.3,
        text=KEP_TEXT,
        canonical_id="kep:2579",
        source_type="kep",
        heading_path=["KEP-2579: Pod Security Admission Control", "Summary"],
        release_windows=[(21, 22), (22, 24), (24, 25), (25, None)],
        claimed_status="implemented",
        claimed_stage="stable",
        snapshot_repo="enhancements",
        snapshot_sha=KEP_SHA,
        source_path="keps/sig-auth/2579-psp-replacement/README.md",
        metadata={"title": "PSP Replacement Policy"},
    )
    return hit.model_copy(update=changes)


HITS_1_2_3 = [_docs_hit(1), _docs_hit(2), _docs_hit(3)]


def _answered(*ids: int) -> ModelAnswer:
    return ModelAnswer(
        answer_status="answered",
        answer="The built-in Pod Security admission controller.",
        evidence=list(ids),
        insufficient_evidence_reason=None,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="x",
        corpus_manifest_path=REAL_MANIFEST,
        generation_model="claude-opus-5-5",
        generation_effort="medium",
        generation_max_tokens=16_000,
    )


# --- The validator (decision 8) ------------------------------------------------------------------


def test_a_citation_outside_the_retrieved_set_is_rejected(settings: Settings) -> None:
    fake = FakeGenerator(_answered(2, 999))

    result = answer(QUESTION, HITS_1_2_3, fake, settings)

    assert result.answer_status == "insufficient_evidence"
    assert result.insufficient_evidence_reason == "citation_validation_failed: [999]"
    assert result.evidence == []
    assert result.answer == ""
    # The rejected answer stays available for the trace.
    assert result.trace is not None
    assert result.trace.generation.output == _answered(2, 999)
    assert result.trace.rejection == "citation_validation_failed: [999]"
    assert result.trace.rejected_ids == [999]


def test_out_of_set_ids_are_listed_once_in_the_models_order() -> None:
    output = _answered(999, 2, 1000, 999)

    assert rejection_reason(output, {1, 2, 3}) == "citation_validation_failed: [999, 1000]"


def test_an_answer_with_no_citations_is_rejected(settings: Settings) -> None:
    result = answer(QUESTION, HITS_1_2_3, FakeGenerator(_answered()), settings)

    assert result.answer_status == "insufficient_evidence"
    assert result.insufficient_evidence_reason == "citation_validation_failed: [no citations]"
    assert result.evidence == []
    assert result.answer == ""


@pytest.mark.parametrize("reason", ["", "  \n", None])
def test_insufficient_evidence_with_an_empty_reason_is_rejected(
    settings: Settings, reason: str | None
) -> None:
    output = ModelAnswer(
        answer_status="insufficient_evidence",
        answer="",
        evidence=[],
        insufficient_evidence_reason=reason,
    )

    result = answer(QUESTION, HITS_1_2_3, FakeGenerator(output), settings)

    assert result.answer_status == "insufficient_evidence"
    assert result.insufficient_evidence_reason == "citation_validation_failed: [empty reason]"


def test_a_valid_answer_citing_1_and_3_passes(settings: Settings) -> None:
    result = answer(QUESTION, HITS_1_2_3, FakeGenerator(_answered(1, 3)), settings)

    assert result.answer_status == "answered"
    assert result.answer == "The built-in Pod Security admission controller."
    assert [e.chunk_id for e in result.evidence] == [1, 3]
    assert result.insufficient_evidence_reason is None
    assert result.trace is not None
    assert result.trace.rejection is None
    assert result.trace.rejected_ids == []


def test_evidence_keeps_the_models_order_and_collapses_duplicates(settings: Settings) -> None:
    result = answer(QUESTION, HITS_1_2_3, FakeGenerator(_answered(3, 1, 3)), settings)

    assert [e.chunk_id for e in result.evidence] == [3, 1]


def test_insufficient_evidence_may_keep_valid_citations(settings: Settings) -> None:
    output = ModelAnswer(
        answer_status="insufficient_evidence",
        answer="",
        evidence=[2],
        insufficient_evidence_reason="The chunks name the controller but not when it shipped.",
    )

    result = answer(QUESTION, HITS_1_2_3, FakeGenerator(output), settings)

    assert result.answer_status == "insufficient_evidence"
    assert [e.chunk_id for e in result.evidence] == [2]
    assert result.insufficient_evidence_reason == (
        "The chunks name the controller but not when it shipped."
    )


# --- Fill-in (decision 7) ------------------------------------------------------------------------


def test_fill_in_a_docs_hit() -> None:
    evidence = fill_in(_docs_hit(), {"website": "https://github.com/kubernetes/website"})

    assert json.loads(evidence.model_dump_json()) == {
        "chunk_id": 551,
        "document": "web:/docs/concepts/security/pod-security-admission/",
        "title": "Pod Security Admission",
        "section": "Exemptions",
        "source_type": "docs_page",
        "release_windows": [["1.30", None]],
        "claimed_status": None,
        "claimed_stage": None,
        "source_url": "https://github.com/kubernetes/website/blob/"
        "c28dcd8393562ddc6adf89b920ad3c396166a31b/"
        "content/en/docs/concepts/security/pod-security-admission.md",
    }


def test_fill_in_a_kep_hit() -> None:
    hit = _kep_hit(release_windows=[(22, 24), (25, None)])

    evidence = fill_in(hit, {"enhancements": "https://github.com/kubernetes/enhancements"})

    assert json.loads(evidence.model_dump_json()) == {
        "chunk_id": 4916,
        "document": "kep:2579",
        "title": "KEP-2579: PSP Replacement Policy",
        "section": "KEP-2579: Pod Security Admission Control > Summary",
        "source_type": "kep",
        "release_windows": [["1.22", "1.24"], ["1.25", None]],
        "claimed_status": "implemented",
        "claimed_stage": "stable",
        "source_url": "https://github.com/kubernetes/enhancements/blob/"
        "0ffd37f8925d8a9af7ce7a7409007db8285a30b1/"
        "keps/sig-auth/2579-psp-replacement/README.md",
    }


def test_the_section_is_null_before_the_first_heading() -> None:
    evidence = fill_in(_docs_hit(heading_path=[]), {"website": "https://example.org"})

    assert evidence.section is None


# --- The prompt (pinned evidence block) ----------------------------------------------------------


def test_the_evidence_block_of_a_docs_hit() -> None:
    hit = _docs_hit(release_windows=[(24, 29), (31, None)])

    assert evidence_block(hit) == (
        "[chunk 551] valid in releases: 1.24\N{EN DASH}1.29, 1.31\N{EN DASH}now\n" + PSA_TEXT
    )


def test_the_evidence_block_of_a_kep_hit() -> None:
    # Windows are printed as the hit lists them: no merging, even where they touch.
    assert evidence_block(_kep_hit()) == (
        "[chunk 4916] valid in releases: "
        "1.21\N{EN DASH}1.22, 1.22\N{EN DASH}1.24, 1.24\N{EN DASH}1.25, 1.25\N{EN DASH}now\n"
        "claimed: implemented/stable\n" + KEP_TEXT
    )


def test_a_one_release_window_prints_once_and_a_missing_claim_prints_none() -> None:
    hit = _kep_hit(release_windows=[(24, 24), (26, None)], claimed_stage=None)

    assert evidence_block(hit) == (
        "[chunk 4916] valid in releases: 1.24, 1.26\N{EN DASH}now\n"
        "claimed: implemented/none\n" + KEP_TEXT
    )


def test_the_prompt_sent_holds_every_block_then_the_question(settings: Settings) -> None:
    fake = FakeGenerator(_answered(551))

    answer(QUESTION, [_docs_hit(), _kep_hit(release_windows=[(25, None)])], fake, settings)

    assert fake.calls == [
        (
            SYSTEM_PROMPT,
            "Evidence:\n\n"
            "[chunk 551] valid in releases: 1.30\N{EN DASH}now\n" + PSA_TEXT + "\n\n"
            "[chunk 4916] valid in releases: 1.25\N{EN DASH}now\nclaimed: implemented/stable\n"
            + KEP_TEXT
            + "\n\nQuestion: What enforces pod security standards in-tree?",
        )
    ]


# --- Failure states (ADR-006 D2) -----------------------------------------------------------------

USAGE = TokenUsage(input_tokens=10, output_tokens=5, thinking_tokens=None)


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_a_refusal_or_a_cut_off_is_a_generation_error(stop_reason: str) -> None:
    # The stop reason alone decides: even a parsed output isn't used.
    generation = Generation(output=_answered(1), stop_reason=stop_reason, usage=USAGE)

    with pytest.raises(GenerationError) as error:
        checked_output(generation)

    assert error.value.stop_reason == stop_reason
    assert error.value.usage == USAGE


def test_no_output_is_a_generation_error() -> None:
    generation = Generation(output=None, stop_reason="end_turn", usage=USAGE)

    with pytest.raises(GenerationError) as error:
        checked_output(generation)

    assert error.value.stop_reason == "end_turn"


def test_a_finished_output_is_returned() -> None:
    generation = Generation(output=_answered(1), stop_reason="end_turn", usage=USAGE)

    assert checked_output(generation) == _answered(1)


def test_answer_raises_a_generation_error_on_a_refusal(settings: Settings) -> None:
    with pytest.raises(GenerationError) as error:
        answer(QUESTION, HITS_1_2_3, FakeGenerator(None, stop_reason="refusal"), settings)

    assert error.value.stop_reason == "refusal"


def test_no_hits_answers_insufficient_evidence_without_calling_the_model(
    settings: Settings,
) -> None:
    fake = FakeGenerator(_answered(1))

    result = answer(QUESTION, [], fake, settings)

    assert fake.calls == []
    assert result.answer_status == "insufficient_evidence"
    assert result.insufficient_evidence_reason == "no evidence retrieved"
    assert result.evidence == []
    assert result.answer == ""
    assert result.trace is None


# --- The printed JSON (pinned format) ------------------------------------------------------------


def test_the_printed_json_has_the_pinned_shape(settings: Settings) -> None:
    result = answer(QUESTION, [_docs_hit()], FakeGenerator(_answered(551)), settings)

    printed = json.loads(result.model_dump_json())

    assert list(printed) == [
        "question",
        "answer_status",
        "answer",
        "evidence",
        "insufficient_evidence_reason",
        "model",
        "trace_id",
    ]
    assert printed == {
        "question": "What enforces pod security standards in-tree?",
        "answer_status": "answered",
        "answer": "The built-in Pod Security admission controller.",
        "evidence": [
            {
                "chunk_id": 551,
                "document": "web:/docs/concepts/security/pod-security-admission/",
                "title": "Pod Security Admission",
                "section": "Exemptions",
                "source_type": "docs_page",
                "release_windows": [["1.30", None]],
                "claimed_status": None,
                "claimed_stage": None,
                "source_url": "https://github.com/kubernetes/website/blob/"
                "c28dcd8393562ddc6adf89b920ad3c396166a31b/"
                "content/en/docs/concepts/security/pod-security-admission.md",
            }
        ],
        "insufficient_evidence_reason": None,
        "model": "claude-opus-5-5",
        "trace_id": None,
    }


# --- AnthropicGenerator, against a mock HTTP transport (no network) ------------------------------


def _client(reply: dict[str, Any], requests: list[httpx2.Request]) -> anthropic.Anthropic:
    """A real SDK client whose HTTP calls are answered by `reply` and recorded."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        return httpx2.Response(200, json=reply)

    return anthropic.Anthropic(
        api_key="test-key",
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
    )


def _reply(
    content: list[dict[str, Any]], stop_reason: str, usage: dict[str, Any]
) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage,
    }


ANSWER_JSON = (
    '{"answer_status": "answered", "answer": "Pod Security admission.", "evidence": [551], '
    '"insufficient_evidence_reason": null}'
)


def test_the_request_and_a_parsed_reply(settings: Settings) -> None:
    requests: list[httpx2.Request] = []
    reply = _reply(
        [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": ANSWER_JSON},
        ],
        "end_turn",
        {
            "input_tokens": 4200,
            "output_tokens": 900,
            "output_tokens_details": {"thinking_tokens": 600},
        },
    )

    generation = AnthropicGenerator(_client(reply, requests), settings).generate("SYS", "PROMPT")

    assert len(requests) == 1
    assert requests[0].url.path == "/v1/messages"
    body = json.loads(requests[0].content)
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == 16_000
    assert body["system"] == "SYS"
    assert body["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["type"] == "json_schema"
    # No temperature (Opus 5.5 rejects it), no thinking setting (always on), no fallbacks.
    assert "temperature" not in body
    assert "thinking" not in body
    assert "fallbacks" not in body
    assert generation == Generation(
        output=ModelAnswer(
            answer_status="answered",
            answer="Pod Security admission.",
            evidence=[551],
            insufficient_evidence_reason=None,
        ),
        stop_reason="end_turn",
        usage=TokenUsage(input_tokens=4200, output_tokens=900, thinking_tokens=600),
    )


def test_a_refusal_reply_has_no_output(settings: Settings) -> None:
    reply = _reply([], "refusal", {"input_tokens": 4200, "output_tokens": 0})
    reply["stop_details"] = {"type": "refusal", "category": None, "explanation": None}

    generation = AnthropicGenerator(_client(reply, []), settings).generate("SYS", "PROMPT")

    assert generation == Generation(
        output=None,
        stop_reason="refusal",
        usage=TokenUsage(input_tokens=4200, output_tokens=0, thinking_tokens=None),
    )


def test_output_cut_off_mid_json_is_a_generation_error(settings: Settings) -> None:
    reply = _reply(
        [{"type": "text", "text": '{"answer_status": "answ'}],
        "max_tokens",
        {"input_tokens": 4200, "output_tokens": 16_000},
    )

    with pytest.raises(GenerationError) as error:
        AnthropicGenerator(_client(reply, []), settings).generate("SYS", "PROMPT")

    # The SDK loses the stop reason and usage on this path (parked, see the brief).
    assert error.value.stop_reason is None
    assert error.value.usage is None
