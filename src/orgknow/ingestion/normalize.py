"""Turn one file (or one KEP's two files) into a content hash and metadata (ADR-002 D2).

A version is a change in normalized content. Normalizing removes what doesn't change meaning:
- front-matter keys on the manifest's strip list (matched case-insensitively, as Hugo does)
- link targets: `[text](url)` hashes as `[text]`, and `[id]: url` as `[id]:`
- whitespace differences, including CRLF and a byte-order mark

Pure functions: bytes in, a FileState out. Raises ValueError for a file that can't be parsed.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import yaml  # type: ignore[import-untyped]

# Front matter: a `---` line (after any blank lines), the YAML, then a closing `---` line.
FRONT_MATTER = re.compile(r"\A(?:[ \t]*\n)*---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
LINK_TARGET = re.compile(r"\]\([^)]*\)")  # [text](url) -> [text]
LINK_DEFINITION = re.compile(r"^(\s*\[[^\]]+\]:)[ \t]*\S.*$", re.M)  # [id]: url -> [id]:


@dataclass(frozen=True)
class FileState:
    """A document's content at one snapshot, as ingestion stores it."""

    content_hash: str
    source_path: str
    metadata: dict[str, Any]  # parsed front matter (or kep.yaml), stripped keys included
    claimed_status: str | None = None  # KEP only (ADR-002 D5)
    claimed_stage: str | None = None
    aliases: tuple[str, ...] = ()  # front-matter `aliases`, as written


def decode(raw: bytes) -> str:
    """UTF-8 text with a byte-order mark removed and CRLF turned into LF."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"not valid UTF-8: {exc}") from exc
    return text.removeprefix("\ufeff").replace("\r\n", "\n")


def _yaml_mapping(text: str, what: str) -> dict[str, Any]:
    try:
        # Only the first YAML document: kep.yaml files can hold more after a `---` line.
        data = next(iter(yaml.safe_load_all(text)), None)
    except yaml.YAMLError as exc:
        raise ValueError(f"{what} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{what} is not a mapping")
    return data


def split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Return (front matter, body). Raises ValueError if there's no parseable front matter."""
    match = FRONT_MATTER.match(text)
    if match is None:
        raise ValueError("no front matter (a `---` block at the top)")
    return _yaml_mapping(match.group(1), "front matter"), text[match.end() :]


def clean_text(body: str) -> str:
    """Drop link targets and collapse whitespace, so link and spacing churn isn't a new version."""
    body = LINK_DEFINITION.sub(r"\1", LINK_TARGET.sub("]", body))
    return " ".join(body.split())


def content_hash(front_matter: Mapping[Any, Any], body: str, strip: frozenset[str]) -> str:
    """SHA-256 of the kept front-matter keys (as sorted JSON), a newline, and the cleaned body.

    `strip` holds lowercase keys. The S02 spike's normalizer computes the same value.
    """
    kept = {str(k): v for k, v in front_matter.items() if str(k).lower() not in strip}
    text = json.dumps(kept, sort_keys=True, default=str) + "\n" + clean_text(body)
    return hashlib.sha256(text.encode()).hexdigest()


def _as_json(mapping: Mapping[Any, Any]) -> dict[str, Any]:
    """The mapping as JSON values, for the `metadata` column (a YAML date becomes a string)."""
    result: dict[str, Any] = json.loads(json.dumps(mapping, default=str))
    return result


def docs_state(path: str, raw: bytes, strip: frozenset[str]) -> FileState:
    """Hash and metadata of a docs page. Raises ValueError if it has no parseable front matter."""
    front_matter, body = split_front_matter(decode(raw))
    lowered = {str(k).lower(): v for k, v in front_matter.items()}
    aliases = lowered.get("aliases") or []
    if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
        raise ValueError(f"front-matter aliases must be a list of strings, not {aliases!r}")
    return FileState(
        content_hash=content_hash(front_matter, body, strip),
        source_path=path,
        metadata=_as_json(front_matter),
        aliases=tuple(aliases),
    )


def _claim(kep_yaml: Mapping[str, Any], key: str, synonyms: Mapping[str, str]) -> str | None:
    """A kep.yaml claim stored as written, except for the ADR-003 D5 synonyms (`GA` -> `stable`)."""
    value = kep_yaml.get(key)
    if value is None:
        return None
    return synonyms.get(str(value), str(value))


def kep_state(
    readme_path: str,
    readme: bytes | None,
    kep_yaml: bytes | None,
    strip: frozenset[str],
    synonyms: Mapping[str, str],
) -> FileState | None:
    """Hash, metadata and claims of a KEP: README + kep.yaml, hashed together.

    A kep.yaml-only change is a new version. `strip` is the manifest's kep_yaml list. Returns
    None if neither file exists; raises ValueError if only one does.
    """
    if readme is None and kep_yaml is None:
        return None
    if kep_yaml is None:
        raise ValueError("README.md has no kep.yaml next to it")
    if readme is None:
        raise ValueError("kep.yaml has no README.md next to it")
    kep = _yaml_mapping(decode(kep_yaml), "kep.yaml")
    return FileState(
        content_hash=content_hash(kep, decode(readme), strip),
        source_path=readme_path,
        metadata=_as_json(kep),
        claimed_status=_claim(kep, "status", synonyms),
        claimed_stage=_claim(kep, "stage", synonyms),
    )
