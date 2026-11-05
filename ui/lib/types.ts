// The API's response shapes (docs/interfaces.md), written by hand to mirror the Python models
// (S17-R1 c3; no code generation). Each type names its model: change both together.

// generation/schema.py
export type AnswerStatus = "answered" | "insufficient_evidence";

// db/models.py: high, observed; low, the KEP's claim.
export type Confidence = "high" | "low";

// `Evidence` (generation/schema.py): one citation, filled in from a retrieved hit.
export type Evidence = {
  chunk_id: number;
  document: string; // the canonical id
  title: string;
  section: string | null; // the heading path joined with " > "; null before any heading
  source_type: string;
  release_windows: [string, string | null][]; // ["1.24", "1.29"]; a null end: still valid
  claimed_status: string | null;
  claimed_stage: string | null;
  tier: number | null; // ADR-003 D3; null: a superseded proposal, or no authority on the hit
  superseded_proposal: boolean;
  effective_stage: string | null; // a KEP's stage at the target release
  stage_confidence: Confidence | null;
  source_url: string;
};

// generation/conflicts.py
export type ConflictKind = "claim_mismatch" | "history_date" | "supersession" | "contradiction";
export type Resolution = "observed_beats_claimed" | "valid_at_target" | "lower_tier" | "unresolved";

// `Conflict` (generation/conflicts.py): one conflict in an answer, found by a rule or the model.
export type Conflict = {
  kind: ConflictKind;
  found_by: "rule" | "model";
  chunk_ids: number[]; // may name chunks that aren't among the answer's citations
  documents: string[]; // the canonical ids of chunk_ids
  summary: string;
  resolution: Resolution;
  prevails: number | null; // the winning chunk (valid_at_target, lower_tier); null otherwise
};

// `Answer` (generation/schema.py): `POST /query`'s 200.
export type Answer = {
  question: string;
  answer_status: AnswerStatus;
  answer: string; // model text: shown only through the formatter (ADR-016 D3)
  evidence: Evidence[];
  conflicts: Conflict[];
  insufficient_evidence_reason: string | null;
  model: string;
  trace_id: string | null;
};

// db/models.py: migration 0008's lists.
export type Step =
  | "problem"
  | "discussion"
  | "proposal"
  | "decision"
  | "implementation"
  | "current_docs";
export type FoundBy = "seed" | "template_field" | "merge_event" | "linking_text" | "similarity";
export type MissingReason =
  | "no_tracking_issue"
  | "no_link"
  | "not_public"
  | "not_ingested"
  | "not_merged"
  | "no_linking_text";

// `ChainStep` (provenance/chain.py). A missing step has only `step` and `missing_reason`.
export type ChainStep = {
  step: Step;
  occurred_at: string | null; // ISO 8601 with its offset (UTC)
  chunk_id: number | null;
  canonical_id: string | null;
  heading_path: string[] | null;
  source_type: string | null;
  source_url: string | null;
  tier: number | null; // at the latest release
  found_by: FoundBy | null;
  via_chunk_id: number | null; // the chunk holding the link that connects this step
  via_canonical_id: string | null;
  via_heading_path: string[] | null;
  missing_reason: MissingReason | null;
};

// `Chain` (provenance/chain.py): `GET /decisions/{canonical_id}`'s 200, 6 steps in step order.
export type Chain = {
  seed: string;
  title: string;
  built_at: string; // ISO 8601 with its offset (UTC)
  steps: ChainStep[];
};

// `DecisionSummary` (db/models.py): one stored chain in `GET /decisions`'s 200, a list
// (ADR-016 D4).
export type DecisionSummary = {
  seed: string;
  title: string;
  built_at: string;
};

// `ERROR_CODES` (api/errors.py).
export type ErrorCode =
  | "invalid_request"
  | "not_found"
  | "upstream_failed"
  | "database_unavailable"
  | "internal";

// `ErrorEnvelope` (api/errors.py): every error response's body.
export type ErrorEnvelope = {
  error: {
    code: ErrorCode;
    message: string; // never shown by the UI (S17-R1 c6)
    request_id: string; // the response's X-Request-ID
  };
};
