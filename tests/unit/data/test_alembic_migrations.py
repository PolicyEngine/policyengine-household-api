from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test__alembic_upgrade_head__creates_expected_analytics_schema(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "analytics.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[3]
    alembic_config = Config(str(repo_root / "alembic.ini"))
    alembic_config.set_main_option(
        "script_location",
        str(repo_root / "alembic"),
    )

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
    assert "request_entity_group" not in variable_columns
    assert "model_entity" not in variable_columns
    assert "model_entity_group" not in variable_columns
