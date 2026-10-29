"""The local cross-encoder behind `Reranker` (S08-T2, ADR-008 D1-D2): RERANK_MODEL
(`BAAI/bge-reranker-base`) at RERANK_REVISION, run on CPU with `transformers` and `torch`.

The only module that imports torch and transformers. `ask` and the eval import it only in rerank
mode, so dense, hybrid and the unit tests never load torch. The recipe is the one the S08-R1
design review's prototype measured, so `make eval-retrieval` reproduces its numbers.
"""

from collections.abc import Sequence

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from orgknow.settings import Settings


class CrossEncoderReranker:
    """The `Reranker` protocol over a sequence classifier with one output: its logit for a
    (question, text) pair is the score, higher meaning more relevant.

    Loading takes 3 s from a warm disk and up to ~26 s cold, so a process builds it once. A model
    missing from the Hugging Face cache is downloaded once, at the pinned revision only; with no
    connection, loading raises OSError. Weights are read from safetensors only.
    """

    def __init__(self, settings: Settings) -> None:
        model, revision = settings.rerank_model, settings.rerank_revision
        self._tokenizer = AutoTokenizer.from_pretrained(model, revision=revision)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model, revision=revision, use_safetensors=True
        ).eval()  # inference: no dropout
        self._max_length = settings.rerank_max_length
        self._batch_size = settings.rerank_batch_size
        # torch's default: the physical cores this process may run on (11 on the design review's
        # laptop, 2 under a 2-CPU `taskset`). Not set here (ADR-008 D2).
        self.threads = torch.get_num_threads()

    def score(self, question: str, texts: Sequence[str]) -> list[float]:
        """One score per text, in the texts' order.

        Texts are scored in batches of RERANK_BATCH_SIZE, shortest first (a stable sort by
        characters), so each batch pads its pairs to similar lengths. Each pair is cut to
        RERANK_MAX_LENGTH tokens, the text losing its end; the header at its start is kept.
        """
        by_length = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        scores = [0.0] * len(texts)
        with torch.inference_mode():  # no gradients: less memory, faster
            for start in range(0, len(by_length), self._batch_size):
                batch = by_length[start : start + self._batch_size]
                inputs = self._tokenizer(
                    [question] * len(batch),
                    [texts[i] for i in batch],
                    padding=True,
                    truncation=True,
                    max_length=self._max_length,
                    return_tensors="pt",
                )
                logits = self._model(**inputs).logits.view(-1).float().tolist()
                for i, logit in zip(batch, logits, strict=True):
                    scores[i] = logit
        return scores
