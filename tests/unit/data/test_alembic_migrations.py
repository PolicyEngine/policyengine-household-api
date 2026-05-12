from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def _alembic_config(repo_root: Path) -> Config:
    alembic_config = Config(str(repo_root / "alembic.ini"))
    alembic_config.set_main_option(
        "script_location",
        str(repo_root / "alembic"),
    )
    return alembic_config


def test__alembic_upgrade_head__creates_expected_analytics_schema(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "analytics.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[3]
    alembic_config = _alembic_config(repo_root)

    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) >= {
        "alembic_version",
        "visits",
        "calculate_requests",
        "calculate_request_variables",
    }

    variable_columns = {
        column["name"]
        for column in inspector.get_columns("calculate_request_variables")
    }
    assert "entity_type" in variable_columns
    assert "variable_name_truncated" in variable_columns
    assert "request_entity_group" not in variable_columns
    assert "model_entity" not in variable_columns
    assert "model_entity_group" not in variable_columns

    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(
            "calculate_request_variables"
        )
    }
    assert (
        "ux_calc_vars_request_variable_entity_source" not in unique_constraints
    )


def test__alembic_downgrade_to_baseline__handles_null_visit_client_ids(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "analytics.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[3]
    alembic_config = _alembic_config(repo_root)

    command.upgrade(alembic_config, "head")

    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO visits "
                "(client_id, datetime, api_version, endpoint, method, "
                "content_length_bytes) "
                "VALUES (NULL, NULL, NULL, NULL, NULL, NULL)"
            )
        )

    command.downgrade(alembic_config, "20260508_0001")

    inspector = inspect(engine)
    client_id_column = next(
        column
        for column in inspector.get_columns("visits")
        if column["name"] == "client_id"
    )
    assert client_id_column["nullable"] is False

    with engine.connect() as connection:
        null_count = connection.execute(
            text("SELECT COUNT(*) FROM visits WHERE client_id IS NULL")
        ).scalar_one()
    assert null_count == 0
