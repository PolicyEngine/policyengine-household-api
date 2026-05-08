-- Analytics DDL for calculate variable usage tracking.
-- Production Cloud SQL deployments should run this once before enabling
-- analytics.collect_variable_usage.

ALTER TABLE visits MODIFY client_id VARCHAR(255) NULL;

CREATE TABLE IF NOT EXISTS calculate_requests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    visit_id INT NOT NULL,
    request_uuid CHAR(36) NOT NULL UNIQUE,
    client_id VARCHAR(255) NULL,
    api_version VARCHAR(32) NULL,
    country_id VARCHAR(16) NOT NULL,
    model_version VARCHAR(64) NULL,
    endpoint VARCHAR(64) NULL,
    method VARCHAR(16) NOT NULL,
    content_length_bytes INT NULL,
    response_status_code INT NULL,
    distinct_variable_count INT NOT NULL DEFAULT 0,
    unsupported_variable_count INT NOT NULL DEFAULT 0,
    deprecated_allowlisted_variable_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_calculate_requests_visit
        FOREIGN KEY (visit_id) REFERENCES visits (id)
);

CREATE INDEX ix_calculate_requests_visit_id
    ON calculate_requests (visit_id);

CREATE INDEX ix_calculate_requests_client_created
    ON calculate_requests (client_id, created_at);

CREATE INDEX ix_calculate_requests_country_created
    ON calculate_requests (country_id, created_at);

CREATE TABLE IF NOT EXISTS calculate_request_variables (
    id INT AUTO_INCREMENT PRIMARY KEY,
    request_id INT NOT NULL,
    client_id VARCHAR(255) NULL,
    created_at DATETIME NOT NULL,
    country_id VARCHAR(16) NOT NULL,
    api_version VARCHAR(32) NULL,
    model_version VARCHAR(64) NULL,
    response_status_code INT NULL,
    variable_name VARCHAR(255) NOT NULL,
    request_entity_group VARCHAR(64) NOT NULL,
    model_entity VARCHAR(64) NULL,
    model_entity_group VARCHAR(64) NULL,
    source VARCHAR(32) NOT NULL,
    period_granularity VARCHAR(16) NOT NULL,
    entity_count INT NOT NULL DEFAULT 0,
    period_count INT NOT NULL DEFAULT 0,
    occurrence_count INT NOT NULL DEFAULT 0,
    availability_status VARCHAR(32) NOT NULL,
    CONSTRAINT fk_calc_vars_request
        FOREIGN KEY (request_id) REFERENCES calculate_requests (id),
    CONSTRAINT ux_calc_vars_request_variable_group_source
        UNIQUE (request_id, variable_name, request_entity_group, source)
);

CREATE INDEX ix_calc_vars_variable_created
    ON calculate_request_variables (variable_name, created_at);

CREATE INDEX ix_calc_vars_client_variable_created
    ON calculate_request_variables (client_id, variable_name, created_at);

CREATE INDEX ix_calc_vars_country_model_variable
    ON calculate_request_variables (country_id, model_version, variable_name);
