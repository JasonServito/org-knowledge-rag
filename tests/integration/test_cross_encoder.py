"""The real cross-encoder (S08-T2): the pinned `BAAI/bge-reranker-base` reads a question about a
feature gate and 3 hand-written texts, and scores highest the one that defines the gate.

Marked `reranker`, and skipped when the pinned model isn't in the local Hugging Face cache, so
CI never downloads it (1.1 GB). It runs under `make test-int` (every test in this folder is
marked `integration`) on a machine where the model is cached. It needs no database.
"""

import pytest
from huggingface_hub import try_to_load_from_cache

from orgknow.settings import Settings

QUESTION = "What does the LegacyServiceAccountTokenCleanUp feature gate do?"
# Hand-written. The gate text is first and the longest, so the scorer, which reads texts
# shortest first, must put each score back in the caller's order for it to come out first.
GATE_TEXT = (
    "LegacyServiceAccountTokenCleanUp: when this feature gate is enabled, the control plane "
    "labels Secret-based service account tokens that no pod has used for a year as invalid, "
    "then deletes them after a further grace period."
)
PODS_TEXT = "A pod runs one or more containers."
TOKENS_TEXT = "Service account tokens are mounted into every pod by default."


@pytest.mark.reranker
def test_the_text_defining_the_gate_scores_highest() -> None:
    settings = Settings(_env_file=None, database_url="unused")  # the pinned model (defaults)
    cached = try_to_load_from_cache(
        settings.rerank_model, "model.safetensors", revision=settings.rerank_revision
    )
    if not isinstance(cached, str):  # None (unknown) or a "known missing" marker
        pytest.skip("the pinned reranker model isn't in the local Hugging Face cache")
    # Imported here, not at the top: collecting this file (`make check` does) never loads torch.
    from orgknow.retrieval.cross_encoder import CrossEncoderReranker

    scores = CrossEncoderReranker(settings).score(QUESTION, [GATE_TEXT, PODS_TEXT, TOKENS_TEXT])

    assert len(scores) == 3
    assert scores[0] > max(scores[1], scores[2])
