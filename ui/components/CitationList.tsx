import Link from "next/link";

import { tierLabel, windowLabel } from "../lib/labels";
import { mergeWindows } from "../lib/timeline";
import type { Evidence } from "../lib/types";

// An answer's citations, in the answer's order. Each shows its chunk number (S17-R1 c5), its
// title (linked to the pinned source) and section, its authority tier, a KEP's claimed status
// and stages, and its release windows, merged (S18-R1 d1: `mergeWindows`). Every value comes from
// the stored text, not the model. A citation whose document is a stored chain's seed
// (`chainSeeds`, from `GET /decisions`) also links to the chain's page; no other citation does
// (ADR-016 D4). Both links open a new tab, so the answer stays on screen (S18-R1 c1).
export function CitationList({
  evidence,
  chainSeeds = [],
}: {
  evidence: Evidence[];
  chainSeeds?: string[];
}) {
  if (evidence.length === 0) {
    return <p>No citations.</p>;
  }
  return (
    <ol className="citations" aria-label="Citations">
      {evidence.map((item) => (
        <li key={item.chunk_id}>
          <div>
            <span className="chunk">chunk {item.chunk_id}</span>{" "}
            <a href={item.source_url} target="_blank" rel="noopener noreferrer">
              {item.title}
            </a>
            {/* A text before its first heading has no section (null): the title alone. */}
            {item.section !== null && <span className="section">{item.section}</span>}
            {chainSeeds.includes(item.document) && (
              <Link
                className="chain-link"
                href={`/decisions/${item.document}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                decision chain
              </Link>
            )}
          </div>
          <div className="badges">
            <span className="badge tier">{tierLabel(item.tier, item.superseded_proposal)}</span>
            {item.claimed_status !== null && (
              <span className="badge stage">claimed status: {item.claimed_status}</span>
            )}
            {item.claimed_stage !== null && (
              <span className="badge stage">claimed stage: {item.claimed_stage}</span>
            )}
            {item.effective_stage !== null && (
              <span className="badge stage">
                effective stage: {item.effective_stage}
                {item.stage_confidence !== null && ` (${item.stage_confidence} confidence)`}
              </span>
            )}
          </div>
          <div className="badges">
            Valid in:
            {/* Merged windows never repeat, but a window holds no id of its own: keyed by position. */}
            {mergeWindows(item.release_windows).map((window, index) => (
              <span key={index} className="badge window">
                {windowLabel(window)}
              </span>
            ))}
          </div>
        </li>
      ))}
    </ol>
  );
}
