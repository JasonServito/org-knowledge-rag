"""The embedding interface (S04-R1 decision 7): texts in, one vector per text out.

`make embed` uses it with `input_type="document"`; retrieval (S04-T5) reuses it for questions
with `input_type="query"`. Tests use a fake with no network (tests/conftest.py).
"""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel

# Every vector has this many numbers: the `embeddings.embedding` column is `vector(1024)`
# (migration 0003), so this is part of the schema, not a setting.
DIMENSIONS = 1024

# Voyage embeds a stored text and a question slightly differently (it adds a short prompt).
InputType = Literal["document", "query"]


class EmbedResult(BaseModel):
    """One request's output."""

    vectors: list[list[float]]  # one per input text, in input order
    total_tokens: int  # the tokens the provider counted (and bills)


class Embedder(Protocol):
    model: str  # the model name; vectors are stored under it

    def embed(self, texts: Sequence[str], input_type: InputType) -> EmbedResult: ...
