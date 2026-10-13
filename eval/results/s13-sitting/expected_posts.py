"""S13-R1 sitting: expected post counts per GitHub item, independent of src/.

Reads the raw API responses from fetch_items.sh (not committed: GitHub text) and
counts the posts T1's rendering keeps: the opening post, plus every human comment,
reply and non-empty review body. Bots are logins ending in "-robot", "-bot" or "[bot]".
Usage: python expected_posts.py <dir from fetch_items.sh>
"""

import json
import sys
from pathlib import Path


def load(path: Path) -> list[dict]:
    """Every object in a file of JSON arrays (`gh api --paginate` concatenates pages)."""
    raw, out, i = path.read_text(), [], 0
    dec = json.JSONDecoder()
    while i < len(raw):
        rest = raw[i:].lstrip()
        if not rest:
            break
        obj, n = dec.raw_decode(rest)
        out += obj if isinstance(obj, list) else [obj]
        i = len(raw) - len(rest) + n
    return out


def is_bot(login: str) -> bool:
    return login.endswith(("-robot", "-bot", "[bot]"))


def main(d: Path) -> None:
    disc = json.loads((d / "disc-1290.json").read_text())["data"]["repository"]["discussion"]
    comments = disc["comments"]["nodes"]
    replies = [r for c in comments for r in c["replies"]["nodes"]]
    dc = [c for c in comments + replies if not is_bot(c["author"]["login"])]
    print(f"sig-release/discussions/1290: 1 opening + {len(dc)} comments and replies "
          f"({len(comments)} comments, {len(replies)} replies, {len(comments) + len(replies) - len(dc)} bot)")

    ic = load(d / "issue-2572-comments.json")
    ih = [c for c in ic if not is_bot(c["user"]["login"])]
    print(f"enhancements/issues/2572: 1 opening + {len(ih)} comments ({len(ic)} total, {len(ic) - len(ih)} bot)")

    pc = load(d / "pr-2567-comments.json")
    ph = [c for c in pc if not is_bot(c["user"]["login"])]
    rv = load(d / "pr-2567-reviews-all.json")
    rb = [r for r in rv if (r["body"] or "").strip() and not is_bot(r["user"]["login"])]
    print(f"enhancements/pull/2567: 1 opening + {len(ph)} comments + {len(rb)} review bodies "
          f"({len(pc)} comments, {len(pc) - len(ph)} bot; {len(rv)} reviews, {len(rb)} with a body)")
    print(f"first comment in 1290: {min(c['createdAt'] for c in comments)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
