"""Canonical document ids (ADR-002 D4): a rendered page by its URL (a blog post by its URL at
publication), a feature gate by its name, a KEP by its number, a governance doc by its repo and
first path."""

DOCS_ROOT = "content/en/"
# The two files of a KEP folder (`keps/<sig>/<number>-<slug>/`); any other file in it is ignored.
KEP_FOLDER_FILES = ("README.md", "kep.yaml")


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


def blog_canonical_id(url: str) -> str:
    """`web:` + the URL a blog post was served at when first published (ADR-002 D4), normalized
    like every web URL: lowercase, with a trailing slash.

    /blog/2020/05/Introducing-PodTopologySpread -> web:/blog/2020/05/introducing-podtopologyspread/
    Raises ValueError if the URL isn't a site path (starting with `/`).
    """
    if not url.startswith("/"):
        raise ValueError(f"blog URL {url!r} is not a site path")
    return f"web:{url.lower().rstrip('/')}/"


def kep_canonical_id(number: int) -> str:
    """`kep:` + the KEP's number (its directory number, also its tracking issue)."""
    return f"kep:{number}"


def kep_file_canonical_id(path: str) -> str:
    """The id of the KEP a file under `keps/<sig>/` belongs to (ADR-002 D4):

    - a folder's README.md or kep.yaml, `keps/<sig>/<number>-<slug>/` -> `kep:<number>`. A folder
      whose slug changes keeps its id (1669, 3257 and 4444 have two names).
    - an old single-file KEP, `keps/<sig>/<name>.md` (no number) -> `kep:<sig>/<name>`, e.g.
      kep:sig-auth/0014-dynamic-audit-configuration (S05-R2 decision 3).

    Raises ValueError, with the reason, for any other file: `keps/sig-network/README.md` is an
    index of the SIG's KEPs.
    """
    parts = path.split("/")
    if parts[0] != "keps":
        raise ValueError("not a KEP: outside keps/")
    if len(parts) == 4 and parts[3] in KEP_FOLDER_FILES:
        number = parts[2].split("-", 1)[0]
        if not number.isdigit():
            raise ValueError(f"KEP folder {parts[2]!r} doesn't start with its number")
        return kep_canonical_id(int(number))
    if len(parts) == 3 and parts[2] == "README.md":
        raise ValueError("an index of the SIG's KEPs, not a KEP")
    if len(parts) == 3 and parts[2].endswith(".md"):
        return f"kep:{parts[1]}/{parts[2].removesuffix('.md')}"
    raise ValueError("not a KEP: neither a KEP folder's README.md or kep.yaml, nor a .md file")


def governance_canonical_id(repo: str, path: str) -> str:
    """`<repo>:<path>` (ADR-002 D4): community:sig-auth/charter.md, or
    sig-release:release-engineering/versioning.md. Ingestion passes a chain's first path."""
    return f"{repo}:{path}"


def gate_canonical_id(title: object) -> str:
    """`gate:` + a feature gate's front-matter `title`, as written: case and typos kept.

    StrictIPCIDRValidation -> gate:StrictIPCIDRValidation. Gate files have no URL (Hugo doesn't
    render them), so the name is the id. Raises ValueError if the title isn't a non-empty string.
    """
    if not isinstance(title, str) or not title.strip():
        raise ValueError(f"a feature gate needs a front-matter title, not {title!r}")
    return f"gate:{title}"
