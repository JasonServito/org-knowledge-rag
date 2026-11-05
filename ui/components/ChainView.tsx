import { utcDate } from "../lib/dates";
import { tierLabel } from "../lib/labels";
import type { Chain, ChainStep } from "../lib/types";

// A stored decision chain (`GET /decisions/{canonical_id}`'s 200): its 6 steps in step order on
// a dated timeline, each with its UTC date (S17-R1 c4). A cited step shows its chunk number, its
// document (linked to the pinned source) and section, its tier, how it was found and the chunk
// holding the link that connects it; a missing step only its reason. Every value comes from the
// stored chain, not a model.
export function ChainView({ chain }: { chain: Chain }) {
  return (
    <article>
      <h2>{chain.title}</h2>
      <p className="built">
        {chain.seed} · built {utcDate(chain.built_at)}
      </p>
      <ol className="chain" aria-label="Steps">
        {chain.steps.map((step) => (
          <li key={step.step} className={step.missing_reason === null ? undefined : "missing"}>
            {step.occurred_at === null ? (
              <span className="step-date">—</span>
            ) : (
              <time className="step-date" dateTime={step.occurred_at}>
                {utcDate(step.occurred_at)}
              </time>
            )}
            <span className="step-name">{step.step}</span>
            <StepSource step={step} />
          </li>
        ))}
      </ol>
    </article>
  );
}

function StepSource({ step }: { step: ChainStep }) {
  // A missing step has only `step` and `missing_reason`; every other field is null.
  if (step.missing_reason !== null) {
    return <div className="missing-reason">missing: {step.missing_reason}</div>;
  }
  return (
    <div>
      <div>
        <span className="chunk">chunk {step.chunk_id}</span>{" "}
        <a className="step-source" href={step.source_url ?? undefined}>
          {step.canonical_id}
        </a>
        {step.heading_path !== null && (
          <span className="section">{step.heading_path.join(" > ")}</span>
        )}
      </div>
      <div className="badges">
        {/* A step carries no superseded flag: no tier shows as "no tier". */}
        <span className="badge tier">{tierLabel(step.tier, false)}</span>
        <span className="badge">found by {step.found_by}</span>
      </div>
      {step.via_chunk_id !== null && (
        <div className="via">
          via chunk {step.via_chunk_id}: {step.via_canonical_id} ›{" "}
          {(step.via_heading_path ?? []).join(" > ")}
        </div>
      )}
    </div>
  );
}
