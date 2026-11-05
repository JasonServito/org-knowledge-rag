"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { FailureMessage } from "../../components/FailureMessage";
import { listDecisions, type ApiResult } from "../../lib/api";
import { utcDate } from "../../lib/dates";
import type { DecisionSummary } from "../../lib/types";

// The Decisions page (`/decisions`; ADR-016 D4): the stored decision chains, as `GET /decisions`
// lists them (by seed), each linked to its page. Read once, in the browser, when the page loads.
export default function DecisionsPage() {
  const [result, setResult] = useState<ApiResult<DecisionSummary[]> | null>(null);

  useEffect(() => {
    listDecisions().then(setResult);
  }, []);

  return (
    <main>
      <h1>Decision chains</h1>
      <DecisionList result={result} />
    </main>
  );
}

function DecisionList({ result }: { result: ApiResult<DecisionSummary[]> | null }) {
  if (result === null) {
    return <p role="status">Loading…</p>;
  }
  if (!result.ok) {
    return <FailureMessage failure={result.failure} />;
  }
  if (result.data.length === 0) {
    return <p>No decision chains are stored. make chains builds them.</p>;
  }
  return (
    <ul className="decisions" aria-label="Decision chains">
      {result.data.map((decision) => (
        <li key={decision.seed}>
          <Link href={`/decisions/${decision.seed}`}>{decision.title}</Link>
          <span className="built">
            {decision.seed} · built {utcDate(decision.built_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}
