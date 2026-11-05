import type { ApiFailure } from "../lib/api";
import type { ErrorCode } from "../lib/types";

// The UI's own message per error code (S17-R1 c6). The API's `message` is never shown: on a 502
// it can carry a provider's text (security review 8.3). The request ID finds the request's
// log lines and trace.
const MESSAGES: Record<ErrorCode, string> = {
  invalid_request: "The API rejected the question as invalid. Check that it isn't empty.",
  not_found: "The API has nothing stored at this address.",
  upstream_failed:
    "The answer failed upstream: the embedding or the model service. Try again in a minute.",
  database_unavailable: "The API can't reach its database. Try again once it's back.",
  internal: "The API hit an unexpected error.",
};

// No answer from the API at all: the browser couldn't reach the UI's server, or the forwarder
// couldn't reach the API or waited past API_TIMEOUT_S.
const NETWORK_MESSAGE =
  "No answer from the API: it isn't running, can't be reached, or took longer than the UI waits.";

export function FailureMessage({ failure }: { failure: ApiFailure }) {
  return (
    <div className="failure" role="alert">
      <p>{failure.kind === "api" ? MESSAGES[failure.code] : NETWORK_MESSAGE}</p>
      {failure.kind === "api" && <p>Request ID: {failure.requestId}</p>}
    </div>
  );
}
