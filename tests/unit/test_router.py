"""The query router (S09-T2, ADR-009): the Claude router's request against a mock HTTP transport,
the eval's stored routes, and `make eval-routes`. No test calls a network.

Expected values are typed by hand: the request fields from the settings each test sets, the
routes from the fakes' tables, the line from the S09-R1 contract's pinned format, and the cost
by hand at $4 / $20 per million tokens.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest
from tests.conftest import FakeRouter

from orgknow.eval import __main__ as eval_main
from orgknow.eval.runner import (
    EvalError,
    load_routes,
    question_key,
    route_missing,
    routes_line,
    save_routes,
)
from orgknow.retrieval.router import SYSTEM_PROMPT, ClaudeRouter, Route, RouterError
from orgknow.settings import Settings

DEMO_GOLDEN = Path(__file__).parents[1] / "fixtures" / "eval" / "demo.yaml"
QUESTION = "Before v1.28, how many minor versions older than kube-apiserver could the kubelet be?"
BEFORE_128 = Route.model_validate(
    {"mode": "HISTORY", "time_scope": {"kind": "before", "start": "1.28", "end": None}}
)
NO_SCOPE = Route.model_validate(
    {"mode": "CURRENT", "time_scope": {"kind": "none", "start": None, "end": None}}
)

# --- ClaudeRouter, against a mock HTTP transport (no network) ------------------------------------


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


def _reply(content: list[dict[str, Any]], stop_reason: str) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 880, "output_tokens": 40},
    }


ROUTE_JSON = '{"mode": "HISTORY", "time_scope": {"kind": "before", "start": "1.28", "end": null}}'


def test_the_request_carries_the_settings_and_the_prompt_and_the_route_comes_back() -> None:
    requests: list[httpx2.Request] = []
    reply = _reply(
        [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": ROUTE_JSON},
        ],
        "end_turn",
    )
    # Not the defaults, so the test sees each value travel from the settings to the request.
    settings = Settings(
        _env_file=None,
        database_url="x",
        router_model="claude-router-test",
        router_effort="high",
        router_max_tokens=1234,
    )
    router = ClaudeRouter(_client(reply, requests), settings)

    route = router.route(QUESTION)
    router.route(QUESTION)

    assert route == BEFORE_128
    assert len(requests) == 2
    assert requests[0].url.path == "/v1/messages"
    body = json.loads(requests[0].content)
    assert body["model"] == "claude-router-test"
    assert body["max_tokens"] == 1234
    assert body["system"] == SYSTEM_PROMPT
    assert body["messages"] == [{"role": "user", "content": QUESTION}]
    assert body["output_config"]["effort"] == "high"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert "temperature" not in body
    assert "thinking" not in body
    assert "fallbacks" not in body
    # The usage of both calls, added up: 2 x 880 in, 2 x 40 out.
    assert (router.input_tokens, router.output_tokens) == (1760, 80)


def test_a_refusal_is_a_router_error_and_its_tokens_still_count() -> None:
    reply = _reply([], "refusal")
    reply["stop_details"] = {"type": "refusal", "category": None, "explanation": None}
    router = ClaudeRouter(_client(reply, []), Settings(_env_file=None, database_url="x"))

    with pytest.raises(RouterError, match=r"no route from the model \(stop reason: refusal\)"):
        router.route(QUESTION)

    assert (router.input_tokens, router.output_tokens) == (880, 40)


# --- The stored routes ---------------------------------------------------------------------------


def test_a_missing_or_empty_route_file_holds_no_routes(tmp_path: Path) -> None:
    path = tmp_path / "claude-opus-5-5.json"
    assert load_routes(path) == {}
    path.write_text("", encoding="utf-8")
    assert load_routes(path) == {}


def test_a_route_file_made_with_another_prompt_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "claude-opus-5-5.json"
    path.write_text(json.dumps({"prompt_sha256": "0" * 64, "routes": {}}), encoding="utf-8")

    with pytest.raises(EvalError) as error:
        load_routes(path)

    assert str(error.value) == (
        f"{path}: made with a different router prompt: delete it and run `make eval-routes`"
    )


def test_the_route_file_records_the_prompt_hash_and_writes_the_same_bytes(tmp_path: Path) -> None:
    one, two = tmp_path / "one.json", tmp_path / "two.json"
    save_routes(one, {"aa": BEFORE_128, "bb": NO_SCOPE})
    save_routes(two, {"bb": NO_SCOPE, "aa": BEFORE_128})

    assert one.read_bytes() == two.read_bytes()
    assert json.loads(one.read_text(encoding="utf-8")) == {
        "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest(),
        "routes": {
            "aa": {
                "mode": "HISTORY",
                "time_scope": {"kind": "before", "start": "1.28", "end": None},
            },
            "bb": {"mode": "CURRENT", "time_scope": {"kind": "none", "start": None, "end": None}},
        },
    }
    assert load_routes(one) == {"aa": BEFORE_128, "bb": NO_SCOPE}


def test_a_stored_route_is_never_requested_again(tmp_path: Path) -> None:
    path = tmp_path / "claude-opus-5-5.json"
    other = "What enforces pod security standards in-tree?"
    save_routes(path, {question_key(QUESTION): BEFORE_128})
    routes = load_routes(path)
    router = FakeRouter({QUESTION: BEFORE_128, other: NO_SCOPE})

    times = route_missing([QUESTION, other], routes, router, path)

    assert router.calls == [other]
    assert len(times) == 1
    assert load_routes(path) == {question_key(QUESTION): BEFORE_128, question_key(other): NO_SCOPE}

    # Everything is stored now: no call.
    assert route_missing([QUESTION, other], load_routes(path), router, path) == []
    assert router.calls == [other]


def test_a_missing_route_with_no_router_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(EvalError, match="1 questions have no stored route and ANTHROPIC_API_KEY"):
        route_missing([QUESTION], {}, None, tmp_path / "routes.json")


class _FailsOnSecond:
    """A router that routes its first question and fails on the next."""

    def __init__(self) -> None:
        self.calls = 0

    def route(self, question: str) -> Route:
        self.calls += 1
        if self.calls > 1:
            raise RouterError("no route from the model (stop reason: refusal)")
        return NO_SCOPE


def test_a_failure_midway_keeps_the_routes_already_paid_for(tmp_path: Path) -> None:
    path = tmp_path / "claude-opus-5-5.json"
    first, second = "What enforces pod security standards in-tree?", QUESTION

    with pytest.raises(EvalError, match=r"routing .* failed: no route from the model"):
        route_missing([first, second], {}, _FailsOnSecond(), path)

    assert load_routes(path) == {question_key(first): NO_SCOPE}


# --- make eval-routes ----------------------------------------------------------------------------


def test_the_routes_line() -> None:
    settings = Settings(_env_file=None, database_url="x")

    # p50 of 1, 2, 4 is 2; the nearest-rank p95 is index ceil(3 x 0.95) - 1 = 2, so 4. Cost:
    # 10,000 x $4 / 1e6 + 1,000 x $20 / 1e6 = $0.04 + $0.02.
    assert routes_line(settings, [1.0, 2.0, 4.0], 40, 10_000, 1_000) == (
        "Routed 3 questions with claude-opus-5-5 (40 already stored). Route time: p50 2.00 s, "
        "p95 4.00 s. Cost $0.06."
    )
    assert routes_line(settings, [], 43, 0, 0) == (
        "Routed 0 questions with claude-opus-5-5 (43 already stored)."
    )


class _Router:
    """`ClaudeRouter`'s stand-in in the command: one route for every question, fixed usage."""

    def __init__(self, client: anthropic.Anthropic, settings: Settings) -> None:
        self.calls: list[str] = []
        self.input_tokens = 0
        self.output_tokens = 0

    def route(self, question: str) -> Route:
        self.calls.append(question)
        self.input_tokens += 1_000
        self.output_tokens += 100
        return NO_SCOPE


def test_eval_routes_fills_the_missing_routes_then_makes_no_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    routers: list[_Router] = []

    def build(client: anthropic.Anthropic, settings: Settings) -> _Router:
        routers.append(_Router(client, settings))
        return routers[-1]

    monkeypatch.setattr(eval_main, "ClaudeRouter", build)
    settings = Settings(
        _env_file=None,
        database_url="x",
        anthropic_api_key="test-key",
        eval_golden_path=DEMO_GOLDEN,
        eval_routes_dir=tmp_path,
        # No conflict set (S10-T6), whatever the repo holds: only the golden questions.
        eval_conflicts_path=tmp_path / "no-conflicts.yaml",
    )

    assert eval_main.main(["routes"], settings) == 0
    # The demo set's 3 questions: 3,000 x $4 / 1e6 + 300 x $20 / 1e6 = $0.018, shown as $0.02.
    assert re.fullmatch(
        r"Routed 3 questions with claude-opus-5-5 \(0 already stored\)\. "
        r"Route time: p50 \d+\.\d\d s, p95 \d+\.\d\d s\. Cost \$0\.02\.\n",
        capsys.readouterr().out,
    )
    assert len(routers[0].calls) == 3
    assert len(load_routes(tmp_path / "claude-opus-5-5.json")) == 3

    # A re-run, even with no key, makes no call.
    no_key = settings.model_copy(update={"anthropic_api_key": None})
    assert eval_main.main(["routes"], no_key) == 0
    assert capsys.readouterr().out == (
        "Routed 0 questions with claude-opus-5-5 (3 already stored).\n"
    )
    assert len(routers) == 1
