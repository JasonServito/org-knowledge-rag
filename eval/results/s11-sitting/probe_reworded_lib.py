import json
import sys
import time
from typing import Literal
import anthropic
import psycopg
from pydantic import BaseModel
from orgknow.cli import load_reranker
from orgknow.db.releases import list_releases
from orgknow.db.retrieval import search, search_lexical
from orgknow.embeddings.voyage import VoyageEmbedder
from orgknow.eval import runner
from orgknow.eval.conflicts import reachable
from orgknow.eval.metrics import score_retrieval
from orgknow.generation.prompt import evidence_block
from orgknow.retrieval.authority import target_release, weigh
from orgknow.retrieval.fusion import fuse
from orgknow.retrieval.rerank import rerank
from orgknow.retrieval.retrieve import attach_authority, retrieve, temporal_plan
from orgknow.settings import Settings
import yaml
from orgknow.retrieval.router import ClaudeRouter

def merged(conn, s, reranker, question, route, window, hits, query_vec, query_text, temporal, latest):
    """hits + the new texts a search for query_text finds under temporal, the new ones scored
    against the ORIGINAL question, weighed, top 10."""
    dense = search(conn, query_vec, s.embedding_model, s.retrieval_candidates, s.hnsw_ef_search, temporal)
    lexical = search_lexical(conn, query_text, s.retrieval_candidates, temporal)
    fused = fuse(dense, lexical, s.rrf_k, len(dense) + len(lexical))
    seen = {h.chunk_id for h in hits}
    new = [h for h in fused if h.chunk_id not in seen]
    if not new:
        return hits
    new = rerank(new, reranker.score(question, [h.text for h in new]), len(new))
    new = attach_authority(conn, new, target_release(route.mode, window, latest))
    return weigh([*hits, *new], route.mode, latest, s.authority_boost, s.authority_demote)[: s.retrieval_top_k]


