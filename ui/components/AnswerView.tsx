import { formatText } from "../lib/format";
import type { Answer } from "../lib/types";
import { CitationList } from "./CitationList";
import { ConflictPanel } from "./ConflictPanel";
import { ReleaseTimeline } from "./ReleaseTimeline";

// One answer (`POST /query`'s 200): the question, the insufficient-evidence state with its
// reason, the answer text through the formatter (ADR-016 D3), the conflicts (none: no panel),
// the citations, then their release windows on a timeline (no citations: none). An
// insufficient-evidence answer can still carry citations (q05 has 1): they show too.
// `chainSeeds`: the stored chains' seeds, for the citations' chain links (none: no links).
export function AnswerView({ answer, chainSeeds = [] }: { answer: Answer; chainSeeds?: string[] }) {
  return (
    <article className="answer">
      <h2>{answer.question}</h2>
      {answer.answer_status === "insufficient_evidence" && (
        <div className="insufficient">
          <h3>Insufficient evidence</h3>
          <p>{answer.insufficient_evidence_reason}</p>
        </div>
      )}
      <div className="answer-text">{formatText(answer.answer)}</div>
      <ConflictPanel conflicts={answer.conflicts} evidence={answer.evidence} />
      <h3>Citations</h3>
      <CitationList evidence={answer.evidence} chainSeeds={chainSeeds} />
      <ReleaseTimeline evidence={answer.evidence} />
    </article>
  );
}
