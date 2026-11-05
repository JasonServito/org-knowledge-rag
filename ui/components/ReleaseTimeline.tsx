import { windowLabel } from "../lib/labels";
import { mergeWindows, placeWindows, releaseAxis } from "../lib/timeline";
import type { Evidence } from "../lib/types";

// The citations' release windows on one release axis (S17-R1 c7): a row per citation, labelled
// with its chunk number, and a bar per window, merged as the citation's badges are (S18-R1 d1:
// `mergeWindows`), so windows that overlap, repeat or follow on make one bar and a gap shows as
// 2 bars. Each row is a CSS grid with one column per release; `placeWindows` gives each bar its
// columns.
export function ReleaseTimeline({ evidence }: { evidence: Evidence[] }) {
  if (evidence.length === 0) {
    return null;
  }
  const axis = releaseAxis(evidence.flatMap((item) => item.release_windows));
  const columns = { gridTemplateColumns: `repeat(${axis.length}, 1fr)` };
  return (
    <section>
      <h3>Release timeline</h3>
      <p className="legend">
        <span className="swatch" /> valid in these releases, both ends included{" "}
        <span className="swatch open" /> still valid (no end yet)
      </p>
      <div className="timeline-row">
        <span className="timeline-label" />
        <div className="timeline-track timeline-axis" style={columns}>
          {axis.map((release) => (
            <span key={release}>{release}</span>
          ))}
        </div>
      </div>
      <ol className="timeline" aria-label="Release timeline">
        {evidence.map((item) => (
          <li key={item.chunk_id} className="timeline-row">
            <span className="timeline-label">chunk {item.chunk_id}</span>
            <div className="timeline-track" style={columns}>
              {/* A window holds no id of its own: keyed by position. */}
              {placeWindows(mergeWindows(item.release_windows), axis).map((segment, index) => (
                <span
                  key={index}
                  className={segment.open ? "segment open" : "segment"}
                  style={{ gridColumn: `${segment.slot + 1} / span ${segment.span}` }}
                  title={
                    segment.open
                      ? `${windowLabel(segment.window)}, still valid`
                      : windowLabel(segment.window)
                  }
                />
              ))}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
