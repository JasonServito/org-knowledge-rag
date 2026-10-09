"""The dense retrieval demo (S04-T5): `uv run python -m orgknow.retrieval.dense "<question>"`
embeds the question, then prints the RETRIEVAL_TOP_K nearest chunk texts with their distances,
whatever RETRIEVAL_MODE says. Paid: one Voyage call per question.

`ask` and the eval retrieve through `retrieval/retrieve.py` (S07-T3), which picks the mode.
"""

import argparse
import sys

import psycopg

from orgknow.db.models import Hit
from orgknow.db.retrieval import search
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.settings import Settings


def _windows(hit: Hit) -> str:
    """Release windows for display, e.g. "1.24-1.24, 1.26-now"."""
    return ", ".join(
        f"1.{start}-{'now' if until is None else f'1.{until}'}"
        for start, until in hit.release_windows
    )


def main(settings: Settings | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print the chunk texts nearest a question.")
    parser.add_argument("question")
    question = parser.parse_args().question
    settings = settings or Settings()
    api_key = settings.voyage_api_key
    if api_key is None or not api_key.get_secret_value():
        sys.exit("VOYAGE_API_KEY is not set: add the key to .env (see .env.example).")
    embedder = VoyageEmbedder(settings.voyage_api_url, api_key, settings.embedding_model)
    vector = embedder.embed([question], "query").vectors[0]
    with psycopg.connect(settings.database_url) as conn:
        hits = search(
            conn, vector, embedder.model, settings.retrieval_top_k, settings.hnsw_ef_search
        )

    for rank, hit in enumerate(hits, start=1):
        section = " > ".join(hit.heading_path) or "(no section)"
        print(
            f"{rank:2}. {hit.distance:.4f}  [chunk {hit.chunk_id}] {hit.canonical_id}\n"
            f"    {section}  |  releases {_windows(hit)}"
        )


if __name__ == "__main__":
    main()
