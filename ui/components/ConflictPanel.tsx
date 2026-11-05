import { formatText } from "../lib/format";
import type { Conflict, ConflictKind, Evidence, Resolution } from "../lib/types";

// Each value in words. A Record per type, so a value added to the type fails the typecheck
// until it has words here.
const KINDS: Record<ConflictKind, string> = {
  claim_mismatch: "claim mismatch",
  history_date: "history date",
  supersession: "supersession",
  contradiction: "contradiction",
};

// generation/conflicts.py (ADR-003 D6): the observed stage or release date beats the KEP's
// claim; else the side valid at the target release prevails; else the lower tier number; else
// unresolved. Only valid_at_target and lower_tier name a winning chunk (`prevails`).
const RESOLUTIONS: Record<Resolution, string> = {
  observed_beats_claimed: "observed beats claimed",
  valid_at_target: "valid at target",
  lower_tier: "lower tier",
  unresolved: "unresolved",
};

// An answer's conflicts (ADR-010 D3), in the answer's order: the kind, who found it, the
// resolution, the summary (model text, so through the formatter, ADR-016 D3), and each side, a
// chunk, by its number (S17-R1 c5). A side among the answer's citations also shows its title; one
// that isn't shows only its number, and the conflict's documents name where it comes from (c9).
// The winning side (`prevails`) is marked; with none, no side is.
export function ConflictPanel({
  conflicts,
  evidence,
}: {
  conflicts: Conflict[];
  evidence: Evidence[];
}) {
  if (conflicts.length === 0) {
    return null;
  }
  const cited = new Map(evidence.map((item) => [item.chunk_id, item]));
  return (
    <section>
      <h3>Conflicts</h3>
      <ol className="conflicts" aria-label="Conflicts">
        {/* Conflicts have no id; the answer's order is fixed: keyed by position. */}
        {conflicts.map((conflict, index) => (
          <li key={index}>
            <div className="badges">
              <span className="kind">{KINDS[conflict.kind]}</span>
              <span className="found-by">
                found by {conflict.found_by === "rule" ? "a rule" : "the model"}
              </span>
              <span className="badge resolution">{RESOLUTIONS[conflict.resolution]}</span>
            </div>
            <div className="summary">{formatText(conflict.summary)}</div>
            <ul className="sides">
              {conflict.chunk_ids.map((chunkId) => {
                const wins = chunkId === conflict.prevails;
                return (
                  <li key={chunkId} className={wins ? "side prevails" : "side"}>
                    <span className="chunk">chunk {chunkId}</span>{" "}
                    <span className="side-source">
                      {cited.get(chunkId)?.title ?? "not among the citations"}
                    </span>
                    {wins && <span className="badge winner">prevails</span>}
                  </li>
                );
              })}
            </ul>
            <p className="documents">Documents: {conflict.documents.join(", ")}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
