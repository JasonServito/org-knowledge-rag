from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from orgknow.ingestion.manifest import Snapshot, load_normalization, load_releases, load_scope

REAL_MANIFEST = Path(__file__).parents[2] / "config" / "corpus_manifest.yaml"
REAL_LOCK = Path(__file__).parents[2] / "config" / "corpus_manifest.lock.yaml"

# Three real entries from the manifest. Each bad list below changes one thing.
R24 = '{version: "1.24", release_date: 2022-05-03, end_of_life: 2023-07-28}'
R25 = '{version: "1.25", release_date: 2022-08-23, end_of_life: 2023-10-28}'
R26 = '{version: "1.26", release_date: 2022-12-08, end_of_life: 2024-02-28}'


def _write_manifest(tmp_path: Path, entries: list[str], latest: str = "1.26") -> Path:
    lines = ["releases:", '  first: "1.24"', f'  latest: "{latest}"', "  list:"]
    lines += [f"    - {entry}" for entry in entries]
    path = tmp_path / "manifest.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_loads_the_real_manifest() -> None:
    releases = load_releases(REAL_MANIFEST)

    # Expected values read by hand from config/corpus_manifest.yaml in the S03-R1 sitting.
    assert len(releases) == 18
    assert [r.minor for r in releases] == list(range(20, 38))
    by_version = {r.version: r for r in releases}
    assert by_version["1.24"].minor == 24
    assert by_version["1.24"].release_date == date(2022, 5, 3)
    assert by_version["1.24"].end_of_life_date == date(2023, 7, 28)
    assert by_version["1.34"].end_of_life_date == date(2026, 10, 27)


def test_accepts_a_good_small_list(tmp_path: Path) -> None:
    # The control for the tests below: without their one change, the list loads.
    releases = load_releases(_write_manifest(tmp_path, [R24, R25, R26]))

    assert [r.version for r in releases] == ["1.24", "1.25", "1.26"]


def test_rejects_a_missing_release(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"contiguous: 1\.26 follows 1\.24"):
        load_releases(_write_manifest(tmp_path, [R24, R26]))


def test_rejects_a_list_that_stops_before_latest(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"releases\.latest \(1\.27\)"):
        load_releases(_write_manifest(tmp_path, [R24, R25, R26], latest="1.27"))


def test_rejects_release_dates_not_ascending(tmp_path: Path) -> None:
    r25_before_r24 = '{version: "1.25", release_date: 2022-04-01, end_of_life: 2023-10-28}'

    with pytest.raises(ValueError, match="strictly ascending"):
        load_releases(_write_manifest(tmp_path, [R24, r25_before_r24, R26]))


def test_rejects_end_of_life_before_release(tmp_path: Path) -> None:
    r25_eol_first = '{version: "1.25", release_date: 2022-08-23, end_of_life: 2022-08-01}'

    with pytest.raises(ValueError, match=r"1\.25: end of life"):
        load_releases(_write_manifest(tmp_path, [R24, r25_eol_first, R26]))


# Unquoted 1.25 is a YAML float, not the string "1.25".
@pytest.mark.parametrize("version", ['"1.25.0"', '"v1.25"', '"1.025"', "1.25"])
def test_rejects_a_version_not_shaped_1_n(tmp_path: Path, version: str) -> None:
    bad = f"{{version: {version}, release_date: 2022-08-23, end_of_life: 2023-10-28}}"

    with pytest.raises(ValidationError, match="version"):
        load_releases(_write_manifest(tmp_path, [R24, bad, R26]))


# --- Scopes and the lock (S04-R1 sitting, pinned `scopes:` block) -------------------------------


def test_loads_the_s04_scope_at_the_locked_shas() -> None:
    scope = load_scope(REAL_MANIFEST, REAL_LOCK, "s04")

    # Expected values read by hand from config/corpus_manifest.yaml (sources.docs_page.sigs.auth,
    # sources.kep.traced) and config/corpus_manifest.lock.yaml.
    assert scope.docs_repo == "website"
    assert scope.docs_paths == (
        "content/en/docs/concepts/security/",
        "content/en/docs/reference/access-authn-authz/",
        "content/en/docs/concepts/policy/pod-security-policy.md",
        "content/en/docs/tasks/configure-pod-container/enforce-standards-admission-controller.md",
        "content/en/docs/tasks/configure-pod-container/enforce-standards-namespace-labels.md",
        "content/en/docs/tasks/configure-pod-container/migrate-from-psp.md",
        "content/en/docs/setup/best-practices/enforcing-pod-security-standards.md",
    )
    # Every release 1.24 -> 1.37; the latest has no release branch, so it is `main`.
    assert [s.release for s in scope.docs_snapshots] == list(range(24, 38))
    assert scope.docs_snapshots[0] == Snapshot(
        24, "release-1.24", "98e2db7d9cc710554b486ad56274e362af03b438"
    )
    assert scope.docs_snapshots[-1] == Snapshot(
        37, "main", "256a1f49419171f6c7fbdb1857146da1c63eb533"
    )
    assert scope.kep_repo == "enhancements"
    assert scope.keps == ((2579, "keps/sig-auth/2579-psp-replacement/"),)
    # Master at each release date 1.20 -> 1.37, then head.
    assert [s.release for s in scope.kep_snapshots] == [*range(20, 38), None]
    assert scope.kep_snapshots[0] == Snapshot(
        20, "master", "2df83383d452cf5dd029de73e1963543dbf37998"
    )
    assert scope.kep_snapshots[-1] == Snapshot(
        None, "master", "4be81e27aef5d252972fd02b5a9479a18982dfe5"
    )
    assert scope.kep_snapshots[-1].label == "head"
    assert scope.docs_snapshots[0].label == "1.24"


def test_an_unknown_scope_is_refused() -> None:
    with pytest.raises(ValueError, match=r"unknown scope 's99'; the manifest has: s04"):
        load_scope(REAL_MANIFEST, REAL_LOCK, "s99")


def test_loads_the_strip_lists_lowercased() -> None:
    strip = load_normalization(REAL_MANIFEST)

    # From config/corpus_manifest.yaml, normalization.strip_front_matter (linkTitle lowercased).
    assert strip["docs_page"] == {
        "reviewers",
        "weight",
        "linktitle",
        "no_list",
        "simple_list",
        "hide_summary",
        "aliases",
    }
    assert strip["kep_yaml"] == {"reviewers", "approvers", "editor", "last-updated"}


def test_a_strip_list_with_a_never_strip_key_is_refused(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "normalization:\n"
        "  never_strip: [title, date]\n"
        "  strip_front_matter:\n"
        "    docs_page: [reviewers, Title]\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"never_strip keys: \['title'\]"):
        load_normalization(manifest)
