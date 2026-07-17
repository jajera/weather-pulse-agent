# Implementation Plan: Weather Pulse NZ

## Overview

Implement the Weather Pulse NZ scheduled agent as a single AWS Lambda (Python 3.14) that orchestrates: parallel Open-Meteo forecast + AQI fetch for 8 NZ cities, compute extremes/aggregates, delta comparison vs DynamoDB, Bedrock narrative digest with template fallback (mood from deltas), S3 raw archive + HTML report, then SNS email and Slack webhook with short Function URL report links. Non-GET on the Function URL returns 405. Infrastructure is defined in Terraform targeting ap-southeast-2. Must-ship report sections only (Hourly Curve and Action Watchouts deferred).

## Tasks

- [x] 1. Set up project structure and configuration
  - [x] 1.1 Create Python project structure with module directories
    - Create `src/` directory with `handler.py`, `config.py`, and subdirectories: `fetch/`, `compute/`, `digest/`, `output/`, `state/` each with `__init__.py`
    - Add `requirements.txt` with dependencies: `boto3`, `urllib3`
    - Add `dev-requirements.txt` with: `pytest`, `hypothesis`, `moto`, `pytest-mock`
    - _Requirements: 12.3_

  - [x] 1.2 Implement configuration module (`src/config.py`)
    - Define `CityConfig` frozen dataclass with `name`, `latitude`, `longitude`, `island` fields
    - Define `WATCHED_CITIES` list with all 8 NZ cities and their exact coordinates per Requirement 2.2
    - Define threshold constants: `WIND_NOTABLE_THRESHOLD_KMH=40`, `AQI_WATCH_THRESHOLD=100`, `AQI_UNHEALTHY_THRESHOLD=150`, `DELTA_TEMP_THRESHOLD_C=5.0`, `DELTA_AQI_THRESHOLD=30`
    - Define timeout constants: `API_TIMEOUT_SECONDS=10`, `BEDROCK_TIMEOUT_SECONDS=30`, `SLACK_TIMEOUT_SECONDS=10`
    - Define AWS resource names/constants: `DYNAMODB_TABLE`, `S3_BUCKET`, `SSM_SLACK_WEBHOOK_PARAM`, `BEDROCK_MODEL_ID`, `AWS_REGION`, `SNS_TOPIC_ARN_ENV`
    - _Requirements: 2.2, 4.4, 4.5, 4.6, 5.2, 12.1_

- [x] 2. Implement data fetching layer
  - [x] 2.1 Implement forecast fetcher (`src/fetch/forecast.py`)
    - Create `fetch_forecast(city: CityConfig) -> dict | None` that calls Open-Meteo forecast API with daily variables (`temperature_2m_max`, `temperature_2m_min`, `wind_gusts_10m_max`, `precipitation_sum`, `weather_code`), hourly variables (`temperature_2m`, `precipitation`), `forecast_days=3`, `forecast_hours=24`, `timezone=Pacific/Auckland`
    - Enforce 10-second timeout per city; return `None` on timeout or HTTP error with logging
    - Create `fetch_all_forecasts(cities: list[CityConfig]) -> dict[str, dict]` that fetches sequentially, skipping failed cities
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 2.2 Implement air quality fetcher (`src/fetch/air_quality.py`)
    - Create `fetch_air_quality(city: CityConfig) -> dict | None` that calls Open-Meteo AQI API with `current=us_aqi,pm2_5` and `timezone=Pacific/Auckland`
    - Enforce 10-second timeout per city; return `None` on timeout or HTTP error with logging
    - Handle null/missing `us_aqi` or `pm2_5` by marking the metric as unavailable
    - Create `fetch_all_air_quality(cities: list[CityConfig]) -> dict[str, dict]` that fetches sequentially, skipping failed cities
    - _Requirements: 3.1, 3.2, 3.3_

  - [x]* 2.3 Write property tests for API URL construction
    - **Property 1: API URL Construction**
    - Test that for any valid CityConfig, forecast URL includes all required daily/hourly variables, correct coordinates, `forecast_days=3`, and `timezone=Pacific/Auckland`; AQI URL includes `us_aqi`, `pm2_5`, and correct coordinates
    - **Validates: Requirements 2.1, 3.1**

  - [x]* 2.4 Write property tests for partial fetch failure resilience
    - **Property 2: Partial Fetch Failure Resilience**
    - Test that for any subset of cities returning errors (with at least one success), the fetch functions return valid data for successful cities without raising exceptions
    - **Validates: Requirements 2.3, 3.2**

  - [x]* 2.5 Write property tests for null AQI field handling
    - **Property 3: Null AQI Field Handling**
    - Test that null/missing `us_aqi` or `pm2_5` marks the metric as unavailable, excludes the city from AQI thresholds, but keeps it in forecast computations
    - **Validates: Requirements 3.3**

- [x] 3. Implement computation layer
  - [x] 3.1 Implement extremes computation (`src/compute/extremes.py`)
    - Create `compute_extremes(city_data: dict) -> dict` that identifies hottest, coldest, windiest, wettest cities using first forecast day values
    - Handle ties by reporting all tied cities in a list
    - Compute largest day-night temperature swing (max of `temperature_2m_max[0] - temperature_2m_min[0]` across cities)
    - Compute island contrast averages (North vs South) for avg max temp, avg min temp, avg max gust
    - Only include cities with valid data in computations
    - _Requirements: 4.1, 4.2, 4.3, 4.7_

  - [x] 3.2 Implement threshold classification (`src/compute/thresholds.py`)
    - Create `classify_thresholds(city_data: dict) -> dict` that returns `wind_watchouts`, `aqi_watch`, and `aqi_unhealthy` lists
    - Wind watchout: first-day `wind_gusts_10m_max[0]` >= 40 km/h
    - AQI watch: 100 <= `us_aqi` < 150
    - AQI unhealthy: `us_aqi` >= 150
    - Ensure no city appears in both `aqi_watch` and `aqi_unhealthy`
    - Exclude cities with unavailable data
    - _Requirements: 4.4, 4.5, 4.6, 4.7_

  - [x] 3.3 Implement delta computation (`src/compute/deltas.py`)
    - Create `compute_deltas(current_payload: dict, previous_payload: dict | None) -> dict` returning a Delta_Record
    - Handle first-run case (`is_first_run=True`, `delta_note="No prior data is available"`)
    - Handle comparison-unavailable case (`comparison_unavailable=True`, `delta_note="Comparison was unavailable"`, empty alert/change lists)
    - Compute `new_alerts` and `cleared_alerts` for `wind_watchouts`, `aqi_watch`, and `aqi_unhealthy` (threshold crossings between runs)
    - Compute `significant_temp_changes` (absolute delta >= 5°C on first-day `temperature_2m_max[0]`)
    - Compute `significant_aqi_changes` (absolute delta >= 30 on `us_aqi`)
    - Compute mood in priority order: `severe` if any current `aqi_unhealthy`; else `quiet` if no new/cleared alerts and all temp/AQI deltas below thresholds; else `notable`
    - _Requirements: 5.1, 5.2, 5.3, 5.5, 10.1_

  - [x]* 3.4 Write property tests for extreme city identification
    - **Property 4: Extreme City Identification**
    - Test that identified extremes have values >= or <= all other cities, and ties include all tied cities
    - **Validates: Requirements 4.1**

  - [x]* 3.5 Write property tests for temperature swing computation
    - **Property 5: Temperature Swing Computation**
    - Test that largest swing equals max(temperature_2m_max[0] - temperature_2m_min[0]) across all cities
    - **Validates: Requirements 4.2**

  - [x]* 3.6 Write property tests for island contrast averaging
    - **Property 6: Island Contrast Averaging**
    - Test that island averages equal arithmetic mean of respective metrics per island group
    - **Validates: Requirements 4.3**

  - [x]* 3.7 Write property tests for threshold classification
    - **Property 7: Threshold Classification**
    - Test wind >= 40 iff flagged, AQI 100-149 iff watch, AQI >= 150 iff unhealthy, no city in both watch and unhealthy
    - **Validates: Requirements 4.4, 4.5, 4.6**

  - [x]* 3.8 Write property tests for missing data exclusion
    - **Property 8: Missing Data Exclusion**
    - Test that cities with unavailable data are never included in extreme/aggregate/threshold results
    - **Validates: Requirements 4.7**

  - [x]* 3.9 Write property tests for delta computation correctness
    - **Property 9: Delta Computation Correctness**
    - Test new/cleared alert logic for wind and AQI categories, and significant first-day temp / AQI change detection matches threshold rules exactly
    - **Validates: Requirements 5.2**

  - [x]* 3.10 Write property tests for quiet mood classification
    - **Property 15: Quiet Mood Classification**
    - Test that when no current `aqi_unhealthy`, no new/cleared alerts, all temp deltas < 5°C, all AQI deltas < 30, mood is "quiet"; and that any current `aqi_unhealthy` yields "severe"
    - **Validates: Requirements 10.1**

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement digest generation layer
  - [x] 5.1 Implement Bedrock narrative generator (`src/digest/bedrock.py`)
    - Create `generate_bedrock_digest(run_payload: dict, delta_record: dict) -> dict | None` that invokes `anthropic.claude-3-haiku-20240307-v1:0` via `bedrock-runtime` client
    - Construct prompt with system instruction (narrate only provided facts) and user message separating data payload from formatting instructions
    - Include city summaries, NZ extremes, delta changes, and threshold flags in data payload
    - Parse response JSON into Executive_Brief structure; return `None` on timeout (30s) or error
    - _Requirements: 6.1, 6.2, 6.3, 6.5_

  - [x] 5.2 Implement template fallback digest (`src/digest/template.py`)
    - Create `generate_template_digest(run_payload: dict, delta_record: dict) -> dict` that always produces a valid Executive_Brief
    - Generate headline (max 120 chars) from extremes data; when mood is `quiet`, headline/bullets must state no major change
    - Generate 3-5 bullets from city conditions, extremes, and island contrast
    - Set mood from `delta_record` mood classification
    - Generate 0-3 watchouts from threshold flags
    - _Requirements: 6.4, 10.1_

  - [x] 5.3 Implement digest orchestrator (`src/digest/__init__.py`)
    - Create `generate_digest(run_payload: dict, delta_record: dict) -> dict` that tries Bedrock first, falls back to template on failure
    - Log which path was taken (Bedrock success vs template fallback)
    - _Requirements: 6.1, 6.4_

  - [x]* 5.4 Write property tests for template fallback validity
    - **Property 10: Template Fallback Produces Valid Executive_Brief**
    - Test that for any valid inputs, template produces headline <= 120 chars, 3-5 bullets, valid mood, 0-3 watchouts
    - **Validates: Requirements 6.4**

  - [x]* 5.5 Write property tests for Bedrock prompt completeness
    - **Property 11: Bedrock Prompt Completeness**
    - Test that constructed prompt contains city summaries, extremes, delta changes, threshold flags, and formatting instructions requesting the Executive_Brief schema
    - **Validates: Requirements 6.3, 6.5**

- [x] 6. Implement output layer
  - [x] 6.1 Implement S3 writer (`src/output/s3_writer.py`)
    - Create `write_raw_json(run_payload: dict, run_timestamp: datetime) -> bool` that writes to `raw/YYYY-MM-DDTHHMMZ.json` (UTC from run timestamp) with `application/json` content type
    - Create `write_html_report(run_payload: dict, delta_record: dict, executive_brief: dict) -> bool` that writes to `reports/latest.html` with `text/html` content type
    - HTML report must contain must-ship sections only: Executive Brief, City Snapshot Board, NZ Extremes, Air Quality Watch, Delta vs Last Run, Sources and Attribution (do not implement Hourly Curve or Action Watchouts)
    - Sources section must include "Open-Meteo", "CC BY 4.0", run timestamp, all 8 city names
    - Log errors and return False on failure; each write is independent and must not raise
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 12.5_

  - [x] 6.2 Implement SNS publisher (`src/output/sns_publisher.py`)
    - Create `publish_sns(executive_brief, run_timestamp, report_url)` that publishes to SNS topic
    - Subject: `Weather Pulse NZ — YYYY-MM-DD` (may include mood)
    - Body: formatted text with headline, bullets, mood, watchouts, and short `…/report` link when available
    - Retry once on failure (immediate → 2s backoff)
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 6.3 Implement Slack poster (`src/output/slack_poster.py`)
    - Create `post_slack(...)` that retrieves webhook URL from SSM and POSTs mood-colored attachment message
    - Include headline, bullets, watchouts, mood sidebar color, and short report link when available
    - 10-second timeout per attempt; retry once on non-2xx or timeout
    - Skip notification and log warning if SSM parameter not found
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x]* 6.4 Write property tests for HTML report section completeness
    - **Property 12: HTML Report Section Completeness**
    - Test that generated HTML contains identifiable sections for all 6 required sections and Sources contains "Open-Meteo", "CC BY 4.0", run timestamp, and all 8 city names
    - **Validates: Requirements 7.3, 7.4**

  - [x]* 6.5 Write property tests for SNS message format
    - **Property 13: SNS Message Format**
    - Test that subject contains "Weather Pulse NZ" and YYYY-MM-DD date, and body contains `reports/latest.html`
    - **Validates: Requirements 8.2, 8.3**

  - [x]* 6.6 Write property tests for Slack message completeness
    - **Property 14: Slack Message Completeness**
    - Test that Slack payload includes headline, all bullets, watchout texts, and report link
    - **Validates: Requirements 9.3**

- [x] 7. Implement state management layer
  - [x] 7.1 Implement DynamoDB state store (`src/state/dynamo.py`)
    - Create `get_snapshot() -> dict | None` that reads item with `pk="latest_snapshot"` and deserializes the JSON-serialized `payload` attribute
    - Create `put_snapshot(run_payload: dict) -> bool` that writes item with `pk="latest_snapshot"`, JSON-serialized full Run_Payload (including extremes and threshold_flags), `run_timestamp`, and TTL (current time + 7 days)
    - Log errors and return None/False on failure; do not raise exceptions
    - _Requirements: 5.1, 5.4, 5.5, 11.5_

- [x] 8. Implement Lambda handler orchestration
  - [x] 8.1 Implement main handler (`src/handler.py`)
    - Dual entry: HTTP GET serves report/assets; non-GET returns 405; schedule invoke runs daily pipeline
    - Parallel forecast + AQI fetch; abort if all forecasts fail
    - Build payload, deltas (mood), digest with mood ownership from Delta_Record
    - S3 writes then SNS/Slack with short report URL when HTML write succeeds
    - Return `statusCode`, `run_timestamp`, `mood`, `report_url`
    - _Requirements: 2.4, 5.5, 6.6, 7.6, 10.2, 10.3, 12.2, 12.3, 12.4, 13_

  - [x] 8.2 Write example-based unit tests for edge cases
    - Include Function URL GET proxy and 405 rejection; report link helpers
    - Coordinate verification, abort paths, first-run deltas, Bedrock fallback, S3/SNS/Slack retries, quiet delivery
    - _Requirements: 2.2, 2.4, 5.3, 5.5, 6.4, 7.5, 7.6, 8.4, 9.4, 9.5, 10.2, 10.3, 13_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implement Terraform infrastructure
  - [x] 10.1 Create Terraform provider and backend configuration (`terraform/main.tf`)
    - Configure AWS provider for `ap-southeast-2` region
    - Define required Terraform version and provider versions
    - _Requirements: 11.2_

  - [x] 10.2 Create Terraform variables and outputs (`terraform/variables.tf`, `terraform/outputs.tf`)
    - Define input variables: email subscription address, project name prefix, environment tag
    - Define outputs: S3 bucket URL, SNS topic ARN, Lambda function ARN, DynamoDB table name
    - _Requirements: 11.1_

  - [x] 10.3 Create DynamoDB table resource (`terraform/dynamodb.tf`)
    - Define `aws_dynamodb_table` with PAY_PER_REQUEST billing, partition key `pk` (String), TTL enabled on `ttl` attribute
    - _Requirements: 11.1, 11.5_

  - [x] 10.4 Create S3 bucket resource (`terraform/s3.tf`)
    - Define `aws_s3_bucket` (private, versioning disabled)
    - Add lifecycle rule for `raw/` prefix with 30-day expiration
    - _Requirements: 11.1_

  - [x] 10.5 Create SNS topic and subscription (`terraform/sns.tf`)
    - Define `aws_sns_topic` (standard)
    - Define `aws_sns_topic_subscription` with email protocol
    - _Requirements: 11.1_

  - [x] 10.6 Create IAM roles and policies (`terraform/iam.tf`)
    - Lambda execution role; least-privilege: DynamoDB GetItem/PutItem, S3 PutObject/GetObject, SNS Publish, SSM GetParameter (webhook + report-link), Bedrock InvokeModel, CloudWatch Logs
    - _Requirements: 11.1, 11.4, 13_

  - [x] 10.7 Create Lambda function resource (`terraform/lambda.tf`)
    - `aws_lambda_function` python3.14, 120s, 256MB + `aws_lambda_function_url` for report/assets
    - Env vars for SNS, S3, DynamoDB, SSM paths / report link
    - _Requirements: 11.1, 11.3, 12.4, 13_

  - [x] 10.8 Create EventBridge Scheduler (`terraform/scheduler.tf`)
    - Define `aws_scheduler_schedule` with `cron(30 6 * * ? *)` expression and `Pacific/Auckland` timezone
    - Configure Lambda as target with appropriate IAM permissions
    - Set retry policy: max 2 retries, 5-minute window (at-least-once delivery within window)
    - _Requirements: 1.1, 1.2, 1.4, 11.1_

  - [x] 10.9 Create SSM parameters (`terraform/ssm.tf`)
    - Slack webhook SecureString placeholder; report-link Function URL base String
    - Document operators replace webhook out of band after deploy
    - _Requirements: 11.1, 13_

  - [x] 10.10 Validate Terraform configuration
    - `terraform validate` / `plan`; IAM includes GetObject; schedule timezone correct; Function URL output present
    - _Requirements: 1.1, 11.1, 11.4, 13_

- [x] 11. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Documentation and demo packaging
  - [x] 12.1 Architecture docs + draw.io (`docs/architecture.md`, `docs/weather-pulse-nz-architecture.drawio`)
  - [x] 12.2 Runbook + Terraform README (`docs/runbook.md`, `terraform/README.md`)
  - [x] 12.3 Demo slideshow + Builder Center draft (`docs/demo/`)
    - Beat table, Playwright report captures, `build-demo.py`, YouTube link
    - _Optional for product runtime; required for challenge submission packaging_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties using Hypothesis
- Example-based unit tests (task 8.2) cover abort paths, retries, quiet-run delivery, and other edge cases from the design testing strategy
- The design specifies Python 3.14 throughout — all code uses type hints compatible with that runtime
- Terraform can proceed in parallel with Python work; Lambda packaging (10.7) needs application code from earlier tasks
- Out of scope for this delivery: Hourly Curve / Action Watchouts report sections, Cognito, Amplify SPA, S3 Vectors, RAG, multi-Lambda fan-out
- Delivery order is fixed: S3 attempts complete, then SNS, then Slack
- Report links use short Function URL (`…/report`); bucket stays private; non-GET → 405
- Mood is always from Delta_Record thresholds/deltas (Requirement 6.6)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.2", "10.1", "10.2"] },
    { "id": 2, "tasks": ["2.3", "2.4", "2.5", "3.1", "3.2", "3.3", "10.3", "10.4", "10.5", "10.9"] },
    { "id": 3, "tasks": ["3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10", "10.6"] },
    { "id": 4, "tasks": ["5.1", "5.2", "7.1", "10.7"] },
    { "id": 5, "tasks": ["5.3", "5.4", "5.5", "10.8"] },
    { "id": 6, "tasks": ["6.1", "6.2", "6.3"] },
    { "id": 7, "tasks": ["6.4", "6.5", "6.6"] },
    { "id": 8, "tasks": ["8.1"] },
    { "id": 9, "tasks": ["8.2", "10.10"] }
  ]
}
```
