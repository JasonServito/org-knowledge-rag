// The formatter for model text (ADR-016 D3): `answer` and conflict summaries. It recognises only
// 3 markdown constructs, the ones the saved answers use: `code spans`, **bold** and lines starting
// with "- " or "* " (bullets). Everything else, including <, >, [text](url) and ![alt](url), is
// text: React escapes it. So it never makes a link, an image or HTML (security review 3.3): no
// dangerouslySetInnerHTML, no markdown library.

import type { ReactElement, ReactNode } from "react";

const BULLET = /^[-*] /;
// Inline, in one line: a code span, or **bold** (which may hold code spans). Whichever opens
// first wins, so `a**b` stays code. An unclosed ` or ** matches nothing and stays text.
const INLINE = /`([^`]+)`|\*\*(.+?)\*\*/g;
const CODE = /`([^`]+)`/g;

// One element per block: a run of bullet lines → a list; any other non-blank line → a paragraph.
export function formatText(text: string): ReactElement[] {
  const blocks: ReactElement[] = [];
  let bullets: ReactElement[] = [];
  text.split("\n").forEach((line, index) => {
    if (BULLET.test(line)) {
      bullets.push(<li key={index}>{formatInline(line.slice(2), INLINE)}</li>);
      return;
    }
    if (bullets.length > 0) {
      blocks.push(<ul key={`list-${index}`}>{bullets}</ul>);
      bullets = [];
    }
    if (line.trim() !== "") {
      blocks.push(<p key={index}>{formatInline(line, INLINE)}</p>);
    }
  });
  if (bullets.length > 0) {
    blocks.push(<ul key="list-end">{bullets}</ul>);
  }
  return blocks;
}

// The line's text between matches stays a string; each match becomes <code> or <strong>.
function formatInline(line: string, pattern: RegExp): ReactNode[] {
  const parts: ReactNode[] = [];
  let end = 0;
  for (const match of line.matchAll(pattern)) {
    const [whole, code, bold] = match;
    parts.push(line.slice(end, match.index));
    parts.push(
      code !== undefined ? (
        <code key={match.index}>{code}</code>
      ) : (
        <strong key={match.index}>{formatInline(bold, CODE)}</strong>
      ),
    );
    end = match.index + whole.length;
  }
  parts.push(line.slice(end));
  return parts;
}
