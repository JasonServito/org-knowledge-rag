"""Canonical document ids (ADR-002 D4): a rendered page by its URL, a feature gate by its name,
a KEP by its number."""

DOCS_ROOT = "content/en/"


def docs_canonical_id(path: str) -> str:
    """`web:` + the URL Hugo renders for a docs file, lowercased, with a trailing slash.

    content/en/docs/concepts/security/overview.md -> web:/docs/concepts/security/overview/
    `_index.md` (a section) and `index.md` (a page bundle) become their folder.
    """
    if not path.startswith(DOCS_ROOT) or not path.endswith(".md"):
        raise ValueError(f"{path} is not an English docs page (content/en/**/*.md)")
    url = "/" + path.removeprefix(DOCS_ROOT).removesuffix(".md")
    folder, _, name = url.rpartition("/")
    if name in ("_index", "index"):
        url = folder
    return f"web:{url.lower()}/"


def alias_id(alias: str) -> str:
    """The id of a front-matter alias: `/rbac/` -> `web:/rbac/`. Only site-absolute aliases."""
    if not alias.startswith("/"):
        raise ValueError(f"relative alias {alias!r} is not supported (S04 has only absolute ones)")
    return f"web:{alias.lower().rstrip('/')}/"


def kep_canonical_id(number: int) -> str:
    """`kep:` + the KEP's number (its directory number, also its tracking issue)."""
    return f"kep:{number}"


def gate_canonical_id(title: object) -> str:
    """`gate:` + a feature gate's front-matter `title`, as written: case and typos kept.

    StrictIPCIDRValidation -> gate:StrictIPCIDRValidation. Gate files have no URL (Hugo doesn't
    render them), so the name is the id. Raises ValueError if the title isn't a non-empty string.
    """
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"a feature gate needs a front-matter title, not {title!r}")
    return f"gate:{title}"
