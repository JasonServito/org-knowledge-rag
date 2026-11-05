"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { ChainView } from "../../../components/ChainView";
import { FailureMessage } from "../../../components/FailureMessage";
import { getDecision, type ApiResult } from "../../../lib/api";
import type { Chain } from "../../../lib/types";

// A decision chain's page (`/decisions/kep:2572`; ADR-016 D1): reads the chain of the address's
// id once, in the browser, then shows it, or a fixed error message (an id with no stored chain:
// the `not_found` one).
export default function DecisionPage() {
  // Next gives the id URI-encoded (`kep%3A3015`); the API client encodes it again for the path.
  const canonicalId = decodeURIComponent(useParams<{ id: string }>().id);
  const [result, setResult] = useState<ApiResult<Chain> | null>(null);

  useEffect(() => {
    getDecision(canonicalId).then(setResult);
  }, [canonicalId]);

  return (
    <main>
      {result === null && <p role="status">Loading…</p>}
      {result !== null &&
        (result.ok ? (
          <ChainView chain={result.data} />
        ) : (
          <FailureMessage failure={result.failure} />
        ))}
    </main>
  );
}
