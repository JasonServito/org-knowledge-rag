"use client";

import { useEffect, useState, type FormEvent } from "react";

import { AnswerView } from "../components/AnswerView";
import { FailureMessage } from "../components/FailureMessage";
import { askQuestion, listDecisions, type ApiResult } from "../lib/api";
import type { Answer } from "../lib/types";

// The answer page (`/`; ADR-016 D1): ask one question, then show the answer or a fixed error
// message. An answer takes ~12 s on the laptop and ~54 s on the AWS server, so while one ask is
// in flight the button is disabled and a working state shows.
export default function AnswerPage() {
  const [question, setQuestion] = useState("");
  const [working, setWorking] = useState(false);
  const [result, setResult] = useState<ApiResult<Answer> | null>(null);
  const [chainSeeds, setChainSeeds] = useState<string[]>([]);

  // The stored chains, read once when the page loads, for the citations' chain links (ADR-016
  // D4). If the list fails, answers still show, without chain links and without an error: the
  // answer is what was asked for.
  useEffect(() => {
    listDecisions().then((listed) => {
      if (listed.ok) {
        setChainSeeds(listed.data.map((decision) => decision.seed));
      }
    });
  }, []);

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorking(true);
    setResult(null);
    setResult(await askQuestion(question));
    setWorking(false);
  }

  return (
    <main>
      <h1>orgknow</h1>
      <form onSubmit={ask}>
        <label htmlFor="question">Question</label>
        <textarea
          id="question"
          rows={3}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button type="submit" disabled={working || question.trim() === ""}>
          {working ? "Working…" : "Ask"}
        </button>
      </form>
      {working && <p role="status">Working… an answer can take up to a minute.</p>}
      {result !== null &&
        (result.ok ? (
          <AnswerView answer={result.data} chainSeeds={chainSeeds} />
        ) : (
          <FailureMessage failure={result.failure} />
        ))}
    </main>
  );
}
