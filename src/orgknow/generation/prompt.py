"""The prompt for the answer step: a fixed system prompt, then one evidence block per hit.

Each block's first line gives the chunk id and every release window of the text (S04-R2
decision 4); a KEP block adds the status and stage the KEP claimed. Pure functions.
"""

from collections.abc import Sequence

from orgknow.db.models import Hit

# Short and plain on purpose: Opus 5.5 does worse with over-prescriptive prompts. It is not asked
# to write out its reasoning (it reasons anyway). The output schema is set by the API call.
SYSTEM_PROMPT = """\
You answer questions about Kubernetes from evidence: chunks of the Kubernetes docs and of KEPs \
(Kubernetes Enhancement Proposals). Each chunk starts with a line giving its id and the releases \
it was valid in ("now": still valid in the latest release). A KEP chunk adds the status and \
stage the KEP claimed.

- Answer only from the evidence, and cite the ids of the chunks that support the answer.
- If the evidence doesn't support an answer, return `insufficient_evidence` with a short reason \
saying what is missing.
- Never state a rationale, motive or history that the evidence doesn't contain.
"""


def _window(start: int, until: int | None) -> str:
    """One release window: from and until joined by an en dash ("now" when still open), or one
    release alone when from and until are the same."""
    if until is None:
        return f"1.{start}\N{EN DASH}now"
    if until == start:
        return f"1.{start}"
    return f"1.{start}\N{EN DASH}1.{until}"


def evidence_block(hit: Hit) -> str:
    """The hit as the model sees it: the id and windows line, a KEP's claim line, the text.

    Windows are printed as the hit lists them, never merged.
    """
    windows = ", ".join(_window(start, until) for start, until in hit.release_windows)
    lines = [f"[chunk {hit.chunk_id}] valid in releases: {windows}"]
    if hit.source_type == "kep":
        status = "none" if hit.claimed_status is None else hit.claimed_status
        stage = "none" if hit.claimed_stage is None else hit.claimed_stage
        lines.append(f"claimed: {status}/{stage}")
    lines.append(hit.text)  # starts with its Source/Title/Document/Section header
    return "\n".join(lines)


def user_prompt(question: str, hits: Sequence[Hit]) -> str:
    """The user message: every evidence block, nearest first, then the question."""
    blocks = "\n\n".join(evidence_block(hit) for hit in hits)
    return f"Evidence:\n\n{blocks}\n\nQuestion: {question}"
