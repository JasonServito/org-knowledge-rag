import operator
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from common import Grade, Step, answer, grade, retrieve, retry_search


class State(TypedDict):
    question: str
    max_retries: int
    retries: int
    hits: list[str]
    grade: Grade | None
    answer: str
    trajectory: Annotated[list[Step], operator.add]


def _retrieve(state: State) -> dict[str, object]:
    hits = retrieve(state["question"])
    return {"hits": hits, "trajectory": [Step("retrieve", f"{len(hits)} hits")]}


def _grade(state: State) -> dict[str, object]:
    g = grade(state["question"], state["hits"])
    return {"grade": g, "trajectory": [Step("grade", g.verdict)]}


def _retry(state: State) -> dict[str, object]:
    g = state["grade"]
    assert g is not None and g.query is not None
    hits = retry_search(state["question"], g.query, state["hits"])
    return {"hits": hits, "retries": state["retries"] + 1, "trajectory": [Step("retry", g.query)]}


def _answer(state: State) -> dict[str, object]:
    return {"answer": answer(state["question"], state["hits"]), "trajectory": [Step("answer", "")]}


def _after_retrieve(state: State) -> Literal["grade", "answer"]:
    return "grade" if state["max_retries"] > 0 else "answer"


def _after_grade(state: State) -> Literal["retry", "answer"]:
    g = state["grade"]
    if g is None or g.verdict != "retry" or g.query is None:
        return "answer"
    return "retry"


def _after_retry(state: State) -> Literal["grade", "answer"]:
    return "grade" if state["retries"] < state["max_retries"] else "answer"


def build() -> "CompiledStateGraph[State, None, State, State]":
    g = StateGraph(State)
    g.add_node("retrieve", _retrieve)
    g.add_node("grade", _grade)
    g.add_node("retry", _retry)
    g.add_node("answer", _answer)
    g.add_edge(START, "retrieve")
    g.add_conditional_edges("retrieve", _after_retrieve)
    g.add_conditional_edges("grade", _after_grade)
    g.add_conditional_edges("retry", _after_retry)
    g.add_edge("answer", END)
    return g.compile()


GRAPH = build()


def corrective(question: str, max_retries: int) -> State:
    initial: State = {"question": question, "max_retries": max_retries, "retries": 0, "hits": [],
                      "grade": None, "answer": "", "trajectory": []}
    result: State = GRAPH.invoke(initial, {"recursion_limit": 4 + 2 * max_retries})
    return result


if __name__ == "__main__":
    print(corrective("q", 2)["trajectory"])
    print(corrective("q", 0)["trajectory"])
