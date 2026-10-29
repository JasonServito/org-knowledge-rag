"""S14-T5: the worker's start-up checks (ADR-013 D2; S14-R2 call f). Both exit before connecting:
the database URL is not one, so a worker that got as far as connecting would fail otherwise.
The messages are typed by hand."""

import pytest
from pydantic import SecretStr

from orgknow.ingestion.worker import main
from orgknow.settings import Settings


def test_the_worker_refuses_a_scope_other_than_full() -> None:
    settings = Settings(
        _env_file=None,
        database_url="not-a-database",
        ingest_scope="s04",
        voyage_api_key=SecretStr("pa-fake-key"),
    )

    with pytest.raises(SystemExit) as exit_info:
        main(settings)

    # sys.exit with a message: the message on stderr, exit status 1.
    assert exit_info.value.code == (
        "The worker runs only with INGEST_SCOPE=full (ADR-013 D2), not s04."
    )


def test_the_worker_needs_a_voyage_key() -> None:
    settings = Settings(
        _env_file=None, database_url="not-a-database", ingest_scope="full", voyage_api_key=None
    )

    with pytest.raises(SystemExit) as exit_info:
        main(settings)

    assert exit_info.value.code == (
        "VOYAGE_API_KEY is not set. The worker's embed step calls the Voyage API: add the key "
        "to .env (see .env.example)."
    )
