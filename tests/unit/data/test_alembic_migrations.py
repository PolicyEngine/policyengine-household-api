from pathlib import Path
from datetime import datetime, timezone

from alembic import command
from alembic.config import Config
from flask import Flask
from sqlalchemy import create_engine, inspect, text

from policyengine_household_analytics.analytics_setup import db
from policyengine_household_analytics.orm import (
    CalculateRequest,
    CalculateRequestVariable,
    Visit,
)


def _alembic_config(repo_root: Path) -> Config:
    alembic_config = Config(
        str(repo_root / "projects" / "analytics-api" / "alembic.ini")
    )
    alembic_config.set_main_option(
        "script_location",
        str(
            repo_root
            / "libs"
            / "household-analytics"
            / "policyengine_household_analytics"
            / "alembic"
        ),
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
    request_columns = {
        column["name"]
        for column in inspector.get_columns("calculate_requests")
    }
    assert "requested_version" in request_columns
    assert "resolved_channel" in request_columns
    assert "requested_version" in variable_columns
    assert "resolved_channel" in variable_columns
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
    variable_indexes = {
        index["name"]
        for index in inspector.get_indexes("calculate_request_variables")
    }
    assert "ix_calc_vars_request_id" in variable_indexes
    assert "ix_calc_vars_channel_created" in variable_indexes
    assert "ix_calc_vars_requested_created" in variable_indexes
    request_indexes = {
        index["name"] for index in inspector.get_indexes("calculate_requests")
    }
    assert "ix_calculate_requests_channel_created" in request_indexes
    assert "ix_calculate_requests_requested_created" in request_indexes


def test__migrated_schema__stores_truncated_variable_name_with_orm(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "analytics.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[3]
    alembic_config = _alembic_config(repo_root)
    command.upgrade(alembic_config, "head")

    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    db.init_app(app)

    stored_name = ("x" * 250) + "..."
    now = datetime.now(timezone.utc)

    with app.app_context():
        try:
            visit = Visit()
            visit.client_id = "test-client"
            visit.datetime = now
            visit.api_version = "1.0.0"
            visit.endpoint = "calculate"
            visit.method = "POST"
            visit.content_length_bytes = 123
            db.session.add(visit)
            db.session.flush()

            request = CalculateRequest()
            request.visit_id = visit.id
            request.request_uuid = "00000000-0000-0000-0000-000000000001"
            request.client_id = "test-client"
            request.api_version = "1.0.0"
            request.country_id = "us"
            request.model_version = "0.0.0"
            request.requested_version = "frontier"
            request.resolved_channel = "frontier"
            request.endpoint = "calculate"
            request.method = "POST"
            request.content_length_bytes = 123
            request.response_status_code = 400
            request.distinct_variable_count = 1
            request.unsupported_variable_count = 1
            request.deprecated_allowlisted_variable_count = 0
            request.created_at = now
            db.session.add(request)
            db.session.flush()

            def variable_row() -> CalculateRequestVariable:
                variable = CalculateRequestVariable()
                variable.request_id = request.id
                variable.client_id = "test-client"
                variable.created_at = now
                variable.country_id = "us"
                variable.api_version = "1.0.0"
                variable.model_version = "0.0.0"
                variable.requested_version = request.requested_version
                variable.resolved_channel = request.resolved_channel
                variable.response_status_code = 400
                variable.variable_name = stored_name
                variable.variable_name_truncated = True
                variable.entity_type = "person"
                variable.source = "household_input"
                variable.period_granularity = "year"
                variable.entity_count = 1
                variable.period_count = 1
                variable.occurrence_count = 1
                variable.availability_status = "unsupported"
                return variable

            db.session.add_all([variable_row(), variable_row()])
            db.session.commit()

            stored_variables = CalculateRequestVariable.query.filter_by(
                variable_name=stored_name
            ).all()
            assert len(stored_variables) == 2
            assert all(
                variable.variable_name == stored_name
                for variable in stored_variables
            )
            assert all(
                len(variable.variable_name) == 253
                for variable in stored_variables
            )
            assert all(
                variable.variable_name_truncated is True
                for variable in stored_variables
            )
            assert all(
                variable.requested_version == "frontier"
                for variable in stored_variables
            )
            assert all(
                variable.resolved_channel == "frontier"
                for variable in stored_variables
            )
        finally:
            db.session.remove()


def test__alembic_downgrade_from_truncation_revision__drops_truncated_rows(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "analytics.db"
    database_url = f"sqlite:///{database_path}"
    monkeypatch.setenv("ANALYTICS_DATABASE_URL", database_url)

    repo_root = Path(__file__).resolve().parents[3]
    alembic_config = _alembic_config(repo_root)
    command.upgrade(alembic_config, "head")

    truncated_name = ("x" * 250) + "..."
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO visits "
                "(id, client_id, datetime, api_version, endpoint, method, "
                "content_length_bytes) "
                "VALUES (1, 'test-client', '2026-05-12 00:00:00', "
                "'1.0.0', 'calculate', 'POST', 123)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO calculate_requests "
                "(id, visit_id, request_uuid, client_id, api_version, "
                "country_id, model_version, endpoint, method, "
                "content_length_bytes, response_status_code, "
                "distinct_variable_count, unsupported_variable_count, "
                "deprecated_allowlisted_variable_count, created_at) "
                "VALUES (1, 1, '00000000-0000-0000-0000-000000000002', "
                "'test-client', '1.0.0', 'us', '0.0.0', 'calculate', "
                "'POST', 123, 400, 3, 2, 0, '2026-05-12 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO calculate_request_variables "
                "(request_id, client_id, created_at, country_id, api_version, "
                "model_version, response_status_code, variable_name, "
                "variable_name_truncated, entity_type, source, "
                "period_granularity, entity_count, period_count, "
                "occurrence_count, availability_status) "
                "VALUES "
                "(1, 'test-client', '2026-05-12 00:00:00', 'us', '1.0.0', "
                "'0.0.0', 400, :truncated_name, 1, 'person', "
                "'household_input', 'year', 1, 1, 1, 'unsupported'), "
                "(1, 'test-client', '2026-05-12 00:00:00', 'us', '1.0.0', "
                "'0.0.0', 400, :truncated_name, 1, 'person', "
                "'household_input', 'year', 1, 1, 1, 'unsupported'), "
                "(1, 'test-client', '2026-05-12 00:00:00', 'us', '1.0.0', "
                "'0.0.0', 400, 'age', 0, 'person', 'household_input', "
                "'year', 1, 1, 1, 'supported')"
            ),
            {"truncated_name": truncated_name},
        )

    command.downgrade(alembic_config, "20260508_0002")

    inspector = inspect(engine)
    variable_columns = {
        column["name"]
        for column in inspector.get_columns("calculate_request_variables")
    }
    assert "variable_name_truncated" not in variable_columns
    assert "requested_version" not in variable_columns
    assert "resolved_channel" not in variable_columns

    with engine.connect() as connection:
        truncated_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM calculate_request_variables "
                "WHERE variable_name = :truncated_name"
            ),
            {"truncated_name": truncated_name},
        ).scalar_one()
        age_count = connection.execute(
            text(
                "SELECT COUNT(*) FROM calculate_request_variables "
                "WHERE variable_name = 'age'"
            )
        ).scalar_one()

    assert truncated_count == 0
    assert age_count == 1


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
