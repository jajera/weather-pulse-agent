# Requirements Document

## Introduction

Weather Pulse NZ is an always-on scheduled agent that fetches daily weather forecasts and air quality data for key New Zealand cities from Open-Meteo, computes deltas against the previous run, generates a human-readable briefing via Amazon Bedrock, and delivers the digest to Slack, email (SNS), and a private S3 HTML report exposed through a short Lambda Function URL. The system runs unattended on a daily schedule aligned to New Zealand local time.

## Glossary

- **Agent**: The Python 3.14 AWS Lambda function that orchestrates each scheduled run
- **Watched_Cities**: The fixed set of eight New Zealand cities monitored each run (Auckland, Hamilton, Tauranga, Wellington, Nelson, Christchurch, Queenstown, Dunedin)
- **Scheduler**: The EventBridge Scheduler rule that triggers the Agent daily at 06:30 Pacific/Auckland
- **Forecast_API**: The Open-Meteo weather forecast HTTP endpoint returning JSON for a given latitude and longitude
- **AQI_API**: The Open-Meteo air quality HTTP endpoint returning JSON for a given latitude and longitude
- **State_Store**: The DynamoDB table holding the last-run snapshot for delta comparison
- **Report_Bucket**: The S3 bucket storing raw JSON archives and the static HTML report
- **Digest_Generator**: The Amazon Bedrock Claude model that narrates structured facts into a human briefing
- **Notification_Topic**: The SNS topic with an email subscription used to deliver the digest
- **Webhook_Parameter**: The SSM SecureString parameter holding the Slack Incoming Webhook URL
- **Report_Link_Base**: The SSM String parameter holding the Lambda Function URL base used for short public report and asset links
- **Report_Function_URL**: The Lambda Function URL that serves `GET /report` (and branding assets) by reading private S3 with IAM
- **Run_Payload**: The structured JSON object containing all fetched and computed data for a single run
- **Delta_Record**: The comparison result between the current Run_Payload and the previous State_Store snapshot
- **Executive_Brief**: A short summary containing one headline, three to five bullets, and an overall mood classification (quiet, notable, or severe); mood is always taken from the Delta_Record, not invented by the Digest_Generator
- **US_AQI**: United States Air Quality Index numeric scale used for threshold evaluation
- **Wind_Notable_Threshold**: Daily maximum wind gust of 40 km/h or greater
- **AQI_Watch_Threshold**: US_AQI value of 100 or greater
- **AQI_Unhealthy_Threshold**: US_AQI value of 150 or greater

## Requirements

### Requirement 1: Daily Scheduled Trigger

**User Story:** As an operations user, I want the agent to run automatically every day at a consistent NZ morning time, so that the briefing is ready before the workday begins.

#### Acceptance Criteria - Requirement 1

1. THE Scheduler SHALL trigger the Agent once per day at 06:30 Pacific/Auckland, maintaining the same local time through NZST and NZDT transitions
2. THE Scheduler SHALL operate in the ap-southeast-2 AWS region
3. WHEN the Scheduler triggers, THE Agent SHALL begin execution within 60 seconds
4. IF the Scheduler invocation fails, THEN THE Scheduler SHALL retry the trigger up to 2 additional times with a maximum retry window of 5 minutes

### Requirement 2: Fetch Weather Forecast Data

**User Story:** As a consumer of the briefing, I want forecast data for all watched NZ cities, so that I can see temperature, wind gust, and precipitation conditions.

#### Acceptance Criteria - Requirement 2

1. WHEN the Agent executes, THE Agent SHALL request from the Forecast_API for each city in Watched_Cities: daily variables (maximum temperature, minimum temperature, maximum wind gust, precipitation sum, and weather code) for the next 3 days, and hourly variables (temperature and precipitation) for the next 24 hours
2. THE Agent SHALL use the following coordinates for Watched_Cities: Auckland (-36.85, 174.76), Hamilton (-37.79, 175.28), Tauranga (-37.69, 176.17), Wellington (-41.29, 174.78), Nelson (-41.27, 173.28), Christchurch (-43.53, 172.64), Queenstown (-45.03, 168.66), Dunedin (-45.87, 170.50)
3. IF a Forecast_API request for a city does not respond within 10 seconds or returns an error, THEN THE Agent SHALL log the error and continue processing remaining cities
4. IF the Agent fails to retrieve forecast data for all cities in Watched_Cities, THEN THE Agent SHALL abort the run and log an error indicating no forecast data was obtained

### Requirement 3: Fetch Air Quality Data

**User Story:** As a health-conscious reader, I want air quality information for each watched city, so that I can decide whether outdoor activity is safe.

#### Acceptance Criteria - Requirement 3

1. WHEN the Agent executes, THE Agent SHALL request current air quality data including US_AQI and PM2.5 from the AQI_API for each city in Watched_Cities using the same coordinates defined in Requirement 2, with a request timeout of 10 seconds per city
2. IF the AQI_API returns an HTTP error, a connection failure, or does not respond within the 10-second timeout for a city, THEN THE Agent SHALL log the error and continue processing remaining cities
3. IF the AQI_API returns a successful response but the US_AQI or PM2.5 value is null or missing for a city, THEN THE Agent SHALL treat that metric as unavailable for the city, log a warning, and continue processing remaining cities

### Requirement 4: Compute NZ Extremes and Aggregates

**User Story:** As a briefing reader, I want to see which NZ cities have the most extreme conditions, so that I can quickly understand nationwide patterns.

#### Acceptance Criteria - Requirement 4

1. WHEN forecast and air quality data are collected, THE Agent SHALL identify the hottest, coldest, windiest, and wettest city among Watched_Cities for that run, where "hottest" means highest daily maximum temperature, "coldest" means lowest daily minimum temperature, "windiest" means highest daily maximum wind gust, and "wettest" means highest daily precipitation sum; IF two or more cities share the same extreme value, THEN THE Agent SHALL report all tied cities for that category
2. WHEN forecast data is collected, THE Agent SHALL compute the largest day-night temperature swing among Watched_Cities, defined as the maximum difference between daily maximum temperature and daily minimum temperature for a single city
3. WHEN forecast data is collected, THE Agent SHALL compute a North Island versus South Island contrast summary comparing average daily maximum temperature, average daily minimum temperature, and average daily maximum wind gust across each island group (North Island: Auckland, Hamilton, Tauranga, Wellington; South Island: Nelson, Christchurch, Queenstown, Dunedin)
4. WHEN daily maximum wind gust for any city is at or above the Wind_Notable_Threshold of 40 km/h, THE Agent SHALL flag that city as a wind watchout
5. WHEN US_AQI for any city is at or above the AQI_Watch_Threshold of 100 and below the AQI_Unhealthy_Threshold of 150, THE Agent SHALL flag that city as an air quality watch
6. WHEN US_AQI for any city is at or above the AQI_Unhealthy_Threshold of 150, THE Agent SHALL flag that city as unhealthy air quality
7. IF forecast or air quality data is unavailable for a city due to an API error, THEN THE Agent SHALL exclude that city from the corresponding extreme and aggregate calculations and SHALL compute results using only the cities with successful data

### Requirement 5: Delta Comparison with Last Run

**User Story:** As a daily reader, I want to know what changed since yesterday, so that I can focus on new developments rather than re-reading static information.

#### Acceptance Criteria - Requirement 5

1. WHEN the Agent completes data aggregation, THE Agent SHALL retrieve the previous run snapshot from the State_Store
2. IF the previous snapshot exists, THEN THE Agent SHALL compute a Delta_Record identifying new alerts (wind or AQI thresholds newly exceeded), cleared alerts (thresholds no longer exceeded), temperature changes of 5 °C or more for any city, and US_AQI changes of 30 or more for any city
3. IF no previous snapshot exists in the State_Store, THEN THE Agent SHALL treat the run as the first run and produce a delta note stating no prior data is available
4. WHEN the Agent completes delta computation, THE Agent SHALL write the current Run_Payload to the State_Store as the new snapshot
5. IF the State_Store retrieval fails, THEN THE Agent SHALL log the error, skip delta computation, and proceed with an empty Delta_Record indicating comparison was unavailable

### Requirement 6: Generate Narrative Digest via Bedrock

**User Story:** As a non-technical reader, I want a natural-language briefing generated from the raw numbers, so that the information is easy to read.

#### Acceptance Criteria - Requirement 6

1. WHEN the Run_Payload and Delta_Record are ready, THE Agent SHALL send the structured facts to the Digest_Generator to produce a human-readable briefing, with a response timeout of 30 seconds
2. THE Digest_Generator SHALL narrate only facts provided by the Agent and SHALL NOT invent data or severity beyond source thresholds
3. THE Agent SHALL provide the Digest_Generator with a prompt that separates data payload from formatting instructions, requesting the Executive_Brief structure: one headline of 120 characters or fewer, three to five bullets, overall mood (quiet, notable, or severe), and up to three top watchouts
4. IF the Digest_Generator returns an error or does not respond within the timeout, THEN THE Agent SHALL fall back to a template-based summary using the structured facts, producing the same Executive_Brief structure as the normal path
5. THE Agent SHALL include in the data payload sent to the Digest_Generator: the Run_Payload city summaries, NZ extremes, Delta_Record changes, and any active threshold flags
6. THE Agent SHALL set Executive_Brief mood from the Delta_Record mood classification after Digest_Generator or template output; Bedrock SHALL NOT be the source of truth for mood

### Requirement 7: Store Raw Archive and HTML Report in S3

**User Story:** As an operator, I want each run's data archived and a readable HTML report available, so that I can audit past runs and share the latest report.

#### Acceptance Criteria - Requirement 7

1. WHEN the Agent completes a run, THE Agent SHALL write the full Run_Payload as JSON to the Report_Bucket at the path `raw/YYYY-MM-DDTHHMMZ.json` using the run timestamp, with Content-Type `application/json`
2. WHEN the Agent completes a run, THE Agent SHALL write a multi-section HTML report to the Report_Bucket at the path `reports/latest.html`, with Content-Type `text/html`
3. THE HTML report SHALL contain at minimum these sections: Executive Brief, City Snapshot Board, NZ Extremes, Air Quality Watch, Delta vs Last Run, and Sources and Attribution
4. THE Sources and Attribution section SHALL credit Open-Meteo with CC BY 4.0, include the run timestamp, and list the cities queried
5. IF writing to the Report_Bucket fails for any object, THEN THE Agent SHALL log the error and continue processing remaining outputs; each S3 write is independent
6. WHEN S3 write attempts for both the raw JSON and the HTML report have completed (successfully or unsuccessfully), THE Agent SHALL proceed to notification delivery

### Requirement 8: Publish Digest to Email via SNS

**User Story:** As a subscriber, I want the daily digest delivered to my email, so that I receive the briefing without visiting a website.

#### Acceptance Criteria - Requirement 8

1. WHEN the Agent completes the digest, THE Agent SHALL publish the Executive_Brief headline, three to five bullets, mood, and up to 3 top watchouts to the Notification_Topic
2. THE SNS message SHALL include a subject line containing "Weather Pulse NZ" and the run date
3. THE email body SHALL include a link to the latest HTML report using the short Report_Function_URL (`…/report`) when available; IF the HTML report write failed, THEN THE Agent SHALL omit the report link or indicate the report is unavailable
4. IF the Notification_Topic publish fails after one retry, THEN THE Agent SHALL log the error and continue execution

### Requirement 9: Post Digest to Slack via Webhook

**User Story:** As a team member, I want the daily digest posted to a Slack channel, so that the team sees weather updates without leaving Slack.

#### Acceptance Criteria - Requirement 9

1. WHEN the Agent completes the digest, THE Agent SHALL retrieve the Slack Incoming Webhook URL from the Webhook_Parameter in SSM
2. WHEN the webhook URL is retrieved, THE Agent SHALL POST the Executive_Brief and top watchouts to the Slack channel within a timeout of 10 seconds
3. THE Slack message SHALL include the Executive_Brief headline, three to five bullets, top watchouts, mood coloring, and a link to the latest HTML report using the short Report_Function_URL (`…/report`) when available
4. IF the Slack POST returns a non-2xx HTTP status or the request exceeds the 10-second timeout, THEN THE Agent SHALL retry the POST once, and if the retry also fails, THE Agent SHALL log the error and continue execution without interrupting the run
5. IF the Webhook_Parameter is not found in SSM, THEN THE Agent SHALL log a warning and skip the Slack notification

### Requirement 10: Quiet Run Handling

**User Story:** As a daily reader, I want to receive a brief note even when nothing significant changed, so that I know the system ran successfully.

#### Acceptance Criteria - Requirement 10

1. WHEN the Delta_Record indicates no new alerts, no cleared alerts, all city temperature changes are less than 5 °C, and all city US_AQI changes are less than 30, THE Agent SHALL classify the run as quiet and produce an Executive_Brief with mood "quiet" stating no major change
2. WHEN the run is quiet, THE Agent SHALL still publish the digest to the Notification_Topic and Slack following the same delivery criteria as Requirements 8 and 9
3. WHEN the run is quiet, THE Agent SHALL still write the raw JSON and HTML report to the Report_Bucket following the same storage criteria as Requirement 7

### Requirement 11: Infrastructure as Code with Terraform

**User Story:** As a developer, I want all infrastructure defined in Terraform, so that the deployment is repeatable and version-controlled.

#### Acceptance Criteria - Requirement 11

1. THE infrastructure code SHALL define all AWS resources (Lambda, Lambda Function URL, EventBridge Scheduler, DynamoDB table, S3 bucket, SNS topic, IAM roles, and SSM parameters) using Terraform; the Slack webhook SecureString parameter SHALL be created with a placeholder value and then updated out of band by operators
2. THE Terraform configuration SHALL deploy to the ap-southeast-2 region
3. THE Lambda function SHALL use Python 3.14 runtime
4. THE IAM roles SHALL follow least-privilege principles, granting each service only the permissions required for its specific function, including S3 PutObject and GetObject for report write/proxy and SSM GetParameter for webhook and Report_Link_Base
5. THE DynamoDB table SHALL use a partition key named `pk` of type String to store the single last-run snapshot item
6. THE Terraform configuration SHALL create a Lambda Function URL and store its base (no trailing slash) in the Report_Link_Base SSM parameter; THE stack output SHALL expose the short `…/report` URL

### Requirement 12: Scope Boundaries

**User Story:** As a project stakeholder, I want clear boundaries on what is in and out of scope, so that the weekend delivery stays focused.

#### Acceptance Criteria - Requirement 12

1. THE Agent SHALL monitor only the eight Watched_Cities defined in this document
2. THE Agent SHALL NOT include global city boards, Cognito authentication, Amplify SPA, S3 Vectors, RAG pipelines, or multi-Lambda notification fan-out
3. THE Agent SHALL operate as a single Lambda function orchestrating all steps (scheduled pipeline and report Function URL handling)
4. THE Agent Lambda SHALL have a maximum execution timeout of 120 seconds
5. THE must-ship report sections SHALL be limited to: Executive Brief, City Snapshot Board, NZ Extremes, Air Quality Watch, Delta vs Last Run, and Sources and Attribution; the Hourly Curve and Action Watchouts sections are deferred as nice-to-have

### Requirement 13: Short Report Link via Function URL

**User Story:** As a reader, I want a short stable report URL in email and Slack, so that I can open the briefing without a long pre-signed S3 URL, while the report objects stay private.

#### Acceptance Criteria - Requirement 13

1. THE Report_Bucket SHALL remain private; notifications SHALL NOT rely on a public-read bucket ACL for the HTML report
2. WHEN HTML report write succeeds, THE Agent SHALL include the short Report_Function_URL path `…/report` in SNS and Slack notifications when Report_Link_Base is configured; IF Report_Link_Base is unavailable, THEN THE Agent MAY fall back to a time-limited pre-signed S3 URL
3. WHEN the Report_Function_URL receives an HTTP GET for `/report` (or equivalent report path), THE Agent SHALL read `reports/latest.html` from the Report_Bucket with IAM and return it as `text/html`
4. WHEN the Report_Function_URL receives an HTTP GET for branding assets (`/favicon.svg`, `/favicon.png`, `/og.jpg`), THE Agent SHALL return the corresponding packaged asset
5. WHEN the Report_Function_URL receives a non-GET HTTP method, THE Agent SHALL return HTTP 405 and SHALL NOT run the daily digest pipeline
6. IF reading `reports/latest.html` fails during a GET proxy, THEN THE Agent SHALL return HTTP 502 with a plain-text unavailable message
