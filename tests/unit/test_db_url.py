import pytest

from orgknow.db.url import with_psycopg_driver


def test_plain_url_gets_psycopg_driver_and_keeps_everything_else() -> None:
    url = "postgresql://orgknow:secret@localhost:5433/orgknow"

    assert with_psycopg_driver(url) == "postgresql+psycopg://orgknow:secret@localhost:5433/orgknow"


@pytest.mark.parametrize(
    "url",
    [
        "postgres://orgknow:secret@localhost/orgknow",  # legacy alias SQLAlchemy rejects
        "postgresql+psycopg2://orgknow:secret@localhost/orgknow",  # driver already chosen
        "",
    ],
)
def test_non_plain_url_is_rejected_without_leaking_password(url: str) -> None:
    with pytest.raises(ValueError, match="must start with postgresql://") as excinfo:
        with_psycopg_driver(url)

    assert "secret" not in str(excinfo.value)
