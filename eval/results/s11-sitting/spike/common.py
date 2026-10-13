"""Shared fakes: the step functions both versions call (stand-ins for retrieve/grade/answer)."""
from dataclasses import dataclass
from typing import Literal

Verdict = Literal["enough", "retry", "stop"]


@dataclass(frozen=True)
class Grade:
    verdict: Verdict
    query: str | None


@dataclass(frozen=True)
class Step:
    """One entry of the trajectory: which step ran, and what it decided."""
    name: str
    detail: str


def retrieve(question: str) -> list[str]:
    return [f"hit for {question}"]


def grade(question: str, hits: list[str]) -> Grade:
    return Grade("retry", "a better query")


def retry_search(question: str, query: str, hits: list[str]) -> list[str]:
    return hits + [f"hit for {query}"]


def answer(question: str, hits: list[str]) -> str:
    return f"answer from {len(hits)} hits"
