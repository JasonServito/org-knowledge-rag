from dataclasses import dataclass, field

from common import Step, answer, grade, retrieve, retry_search


@dataclass
class Result:
    answer: str
    hits: list[str]
    trajectory: list[Step] = field(default_factory=list)


def corrective(question: str, max_retries: int) -> Result:
    """Retrieve, then grade and retry at most `max_retries` times, then answer."""
    hits = retrieve(question)
    trajectory = [Step("retrieve", f"{len(hits)} hits")]
    for _ in range(max_retries):
        g = grade(question, hits)
        trajectory.append(Step("grade", g.verdict))
        if g.verdict != "retry" or g.query is None:
            break
        hits = retry_search(question, g.query, hits)
        trajectory.append(Step("retry", g.query))
    trajectory.append(Step("answer", ""))
    return Result(answer(question, hits), hits, trajectory)


if __name__ == "__main__":
    print(corrective("q", 2))
    print(corrective("q", 0))
