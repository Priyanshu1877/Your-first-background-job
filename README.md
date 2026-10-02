# FlyRank Backend AI Engineering: BE-06 — Your First Background Job

A robust background job processing service built with **Python 3.10+**, **FastAPI**, and **Inngest**. This project demonstrates how modern backend systems decouple slow work from HTTP request handlers by accepting requests immediately with an **HTTP 202 Accepted** response, executing durable multi-step workflows in background jobs, providing client status polling, managing automatic retries with backoff, and scheduling cron heartbeat tasks on the clock alone.

---

## Architecture & Workflow

### 1. Request / Background Job Lifecycle

When an API performs slow operations (e.g. data exports, AI model generation, PDF rendering), holding HTTP connections open causes client timeouts, connection pool exhaustion, and duplicate work.

This service implements the standard **Accept Fast → Work in Background → Report Status** lifecycle:

```
[Client]
   |
   |-- (1) POST /reports {"topic":"cats"} ----------------------------> [FastAPI Server]
   |<-- (2) 202 Accepted {"id":"...", "status":"pending"} (<10ms) -----|
   |                                                                   |
   |                                                      (3) Dispatches Event:
   |                                                          report/requested
   |                                                                   v
   |                                                          [Inngest Dev Server]
   |                                                                   |
   |                                                      (4) Step 1: do-the-slow-work
   |                                                          (~8-second durable sleep)
   |                                                                   |
   |                                                      (5) Step 2: build-report
   |                                                          (generates analysis &
   |                                                           updates store status to 'done')
   |                                                                   v
   |-- (6) GET /reports/{id} [Immediate Poll] ------------------------> [FastAPI Server]
   |<-- Returns {"status":"pending", "result":null} -------------------|
   |
   |   ... ~8–10 seconds later ...
   |
   |-- (7) GET /reports/{id} [Eventual Consistency Poll] -------------> [FastAPI Server]
   |<-- Returns {"status":"done", "result":"Summary report on..."} ----|
```

### 2. Autonomous Scheduled Heartbeat Workflow

The `heartbeat` function operates completely decoupled from HTTP traffic:
- Driven exclusively by Inngest's scheduler on a clock schedule (`* * * * *`).
- Directly inspects the in-memory store.
- Summarizes and logs pending, done, and failed metrics every minute.

---

## Prerequisites

Before running the project, ensure you have:
- **Python**: 3.10+ (tested on Python 3.14.3)
- **Node.js & npm / npx**: Required to launch the local Inngest Dev Server CLI (`npx inngest-cli@latest`)
- **Git**: For version control

---

## Installation (Under 5 Minutes)

### Windows (PowerShell)

```powershell
# Navigate into the project folder
cd week7-background-job

# 1. Create Python virtual environment
python -m venv .venv

# 2. Activate virtual environment
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt
```

### macOS / Linux (Bash)

```bash
# Navigate into the project folder
cd week7-background-job

# 1. Create Python virtual environment
python3 -m venv .venv

# 2. Activate virtual environment
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Two Run Commands

To run the complete system locally, keep two terminal windows open:

### Terminal 1 — Start FastAPI Server

```powershell
.\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000
```
- API Base URL: `http://127.0.0.1:8000`
- Health Probe: `http://127.0.0.1:8000/health`

### Terminal 2 — Start Inngest Dev Server

```powershell
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest
```
- Local Inngest Dev Server & Web UI: **[http://localhost:8288](http://localhost:8288)**

---

## API Endpoints

| Method | Endpoint | Purpose | Expected Status |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Health check probe | `200 OK` |
| `POST` | `/reports` | Queue report job (rejects missing topic immediately) | `202 Accepted` / `400 Bad Request` |
| `GET` | `/reports/{id}` | Poll report status (`pending` initially, `done` + `result` after completion) | `200 OK` / `404 Not Found` |
| `GET` / `POST` | `/api/inngest` | Inngest function serving, introspection, and communication endpoint | Inngest protocol (`200 OK` / `206 Partial Content`) |

---

## Inngest Functions

| Function | Trigger | Retries | Steps | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `say-hello` | `test/hello` | Default | 1. `sleep-5s` (5s durable sleep) | Stage 1 introductory background function returning greeting |
| `make-report` | `report/requested` | `2` (3 total attempts) | 1. `do-the-slow-work` (~8s sleep)<br>2. `build-report` (generates result & marks `done`) | Stage 2 & 3 core background report generation job |
| `heartbeat` | `* * * * *` (cron) | Default | 1. `log-summary` (aggregates store counts) | Stage 4 autonomous every-minute report status monitor |

---

## Stage 2 Proof: Fast 202 Response & Eventual Consistency Polling

The following actual trace was recorded live against the local FastAPI service and Inngest Dev Server:

### 1. Fast POST /reports (Returned in 7.64 ms)
```http
POST /reports HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{"topic": "cats"}

HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "id": "27fc77eb-58cd-40a7-928a-db240f938cc1",
  "status": "pending"
}
```
*Elapsed Time: **7.64 ms** (well under 1 second; slow work was completely offloaded).*

### 2. Immediate Poll (Returns Pending)
```http
GET /reports/27fc77eb-58cd-40a7-928a-db240f938cc1 HTTP/1.1
Host: 127.0.0.1:8000

HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "27fc77eb-58cd-40a7-928a-db240f938cc1",
  "topic": "cats",
  "status": "pending",
  "result": null
}
```

### 3. Eventual Consistency Poll (~9.5s Later — Returns Done + Result)
```http
GET /reports/27fc77eb-58cd-40a7-928a-db240f938cc1 HTTP/1.1
Host: 127.0.0.1:8000

HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": "27fc77eb-58cd-40a7-928a-db240f938cc1",
  "topic": "cats",
  "status": "done",
  "result": "Summary report on 'cats': Detailed intelligence and data analysis completed."
}
```

---

## Stage 3 Proof: Retries vs. Bad Input Validation

> **"Bad input is rejected at the door; transient background failures are retried."**

### 1. Bad Input Rejection at the HTTP Door (HTTP 400)
When a request omits the `topic` field or provides an empty/whitespace string, the API rejects it immediately with **HTTP 400 Bad Request**:
```http
POST /reports HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json

{}

HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "detail": "Field 'topic' is required and cannot be empty"
}
```
- **Result**: No database record created in `reports_db`. No Inngest event dispatched. Malformed input is not retried.

### 2. Transient Background Failures & Automatic Retries (`topic == "fail"`)
When `topic == "fail"`, the `build-report` step deliberately raises:
```python
raise Exception("The report oven is broken!")
```
- **Configuration**: `retries = 2`
- **Attempts**: 1 initial attempt + 2 retries = **3 total attempts**
- **Observed Live Execution (Run `01M3XPDXZKF86PW6KXX14CKBPY`)**:
  - `Attempt 1`: `06:57:12 UTC` → Failed (`"The report oven is broken!"`)
  - `Attempt 2`: `06:57:32 UTC` → Failed after exponential backoff
  - `Attempt 3`: `06:58:06 UTC` → Failed after second backoff
  - `Final State`: Retries exhausted → Status permanently transitions to **Failed** (`inngest/function.failed`).

---

## Stage 4 Proof: Scheduled Cron Heartbeat

The `heartbeat` function runs without incoming HTTP requests or event triggers, relying solely on the Inngest cron clock.

### 1. Live Verification Output
- **Testing Schedule**: `* * * * *` (every minute)
- **Live Runs Observed**: 6 consecutive runs executed at `07:13:00`, `07:14:00`, `07:15:00`, `07:16:00`, `07:17:00`, and `07:18:00 UTC` (exactly 1 minute apart).
- **Console Log Output**:
  ```
  Heartbeat: pending=0 done=2 failed=0
  ```

### 2. Cron Syntax Reference

Standard 5-field cron format: `minute hour day-of-month month day-of-week`

- **Every day at 08:00**:
  ```
  0 8 * * *
  ```
  Runs at minute `0`, hour `8` (08:00 AM), every day of month (`*`), every month (`*`), every day of week (`*`).

- **Every Sunday at 22:00**:
  ```
  0 22 * * 0
  ```
  Runs at minute `0`, hour `22` (10:00 PM), every day of month (`*`), every month (`*`), on Sunday (`0`).

> **Timezone Consideration**: Server operating systems and cloud job runners execute cron schedules in **UTC** by default. Always verify your server's timezone settings and convert desired local business hours to UTC (or specify the timezone explicitly via prefix, e.g. `TZ=America/New_York 0 8 * * *`).

---

## Inngest Dashboard Evidence Portfolio

The screenshots below verify all four stages running in the local Inngest Dev Server UI:

### Stage 1 — Say Hello Completed (5s Sleep)
![Stage 1 Say Hello Completed](screenshots/stage1_say_hello_completed.png)
*Run `01M3XN4A9K9XBYNC2G1S6A1RRT` showing the `sleep-5s` durable step (5.000s) and `"Hello from the background!"` output.*

### Stage 2 — Report Completed (Two Distinct Steps)
![Stage 2 Report Completed](screenshots/stage2_report_completed.png)
*Run `01M3XNP94JGSGJAJ7QG6W5EVHZ` showing both `do-the-slow-work` (8.000s sleep) and `build-report` (4ms execution) steps completing successfully.*

### Stage 3 — Retries and Final Failure (3 Attempts)
![Stage 3 Retry Failed](screenshots/stage3_retry_failed.png)
*Run `01M3XPDXZKF86PW6KXX14CKBPY` showing all 3 attempts failing with exponential backoff and error `"The report oven is broken!"`.*

### Stage 4 — Cron Heartbeat Runs (1-Minute Intervals)
![Stage 4 Cron Heartbeat](screenshots/stage4_heartbeat.png)
*Heartbeat function triggered by `* * * * *` showing multiple consecutive runs executed 1 minute apart.*

---

## Automated Test Results

The project contains comprehensive unit and integration tests across all stages.

```powershell
.\.venv\Scripts\pytest -v
```

**Output**:
```
tests/test_stage0_health.py::test_health_check_returns_200_and_ok PASSED [  5%]
tests/test_stage1_inngest.py::test_inngest_client_configuration PASSED   [ 10%]
tests/test_stage1_inngest.py::test_inngest_endpoint_reachable PASSED     [ 15%]
tests/test_stage1_inngest.py::test_say_hello_configuration PASSED        [ 20%]
tests/test_stage1_inngest.py::test_say_hello_execution_logic[asyncio] PASSED [ 25%]
tests/test_stage2_reports.py::test_post_reports_returns_202_id_and_pending PASSED [ 30%]
tests/test_stage2_reports.py::test_post_reports_fast_response_no_slow_work PASSED [ 35%]
tests/test_stage2_reports.py::test_get_report_returns_pending_initially PASSED [ 40%]
tests/test_stage2_reports.py::test_get_unknown_report_returns_404 PASSED [ 45%]
tests/test_stage2_reports.py::test_make_report_execution_workflow_and_completion[asyncio] PASSED [ 50%]
tests/test_stage2_reports.py::test_make_report_configuration PASSED      [ 55%]
tests/test_stage3_retries_validation.py::test_post_reports_missing_topic_returns_400 PASSED [ 60%]
tests/test_stage3_retries_validation.py::test_missing_topic_does_not_create_report PASSED [ 65%]
tests/test_stage3_retries_validation.py::test_missing_topic_does_not_send_event PASSED [ 70%]
tests/test_stage3_retries_validation.py::test_make_report_configured_with_retries_2 PASSED [ 75%]
tests/test_stage3_retries_validation.py::test_make_report_fail_topic_raises_error[asyncio] PASSED [ 80%]
tests/test_stage4_heartbeat.py::test_heartbeat_function_exists_and_id PASSED [ 85%]
tests/test_stage4_heartbeat.py::test_heartbeat_cron_trigger_schedule PASSED [ 90%]
tests/test_stage4_heartbeat.py::test_heartbeat_no_http_or_event_trigger PASSED [ 95%]
tests/test_stage4_heartbeat.py::test_heartbeat_counts_pending_done_failed[asyncio] PASSED [100%]

======================= 20 passed, 2 warnings in 1.12s ========================
```

---

## Project Structure

```
week7-background-job/
├── app/
│   ├── __init__.py           # App package indicator
│   ├── main.py               # FastAPI application, routing (/health, /reports, /reports/{id}), and /api/inngest mounting
│   ├── inngest_client.py     # Inngest client configured with app_id="report-api" and dev mode
│   ├── functions.py          # Inngest functions: say-hello, make-report (2 steps, retries=2), and heartbeat (cron)
│   ├── reports.py            # In-memory thread-safe report store and CRUD helpers
│   └── models.py             # Pydantic schemas for requests and responses
├── tests/
│   ├── __init__.py           # Tests package indicator
│   ├── test_stage0_health.py             # Health check endpoint test
│   ├── test_stage1_inngest.py            # Inngest client, endpoint reachability, and say-hello tests
│   ├── test_stage2_reports.py            # Fast 202 response, step execution, and polling tests
│   ├── test_stage3_retries_validation.py # HTTP 400 validation and retry configuration tests
│   └── test_stage4_heartbeat.py          # Cron schedule, metrics calculation, and trigger isolation tests
├── screenshots/
│   ├── stage1_say_hello_completed.png    # Live proof: say-hello 5s sleep completion
│   ├── stage2_report_completed.png       # Live proof: make-report 2-step completion
│   ├── stage3_retry_failed.png           # Live proof: 3 attempts with backoff ending in Failed
│   └── stage4_heartbeat.png              # Live proof: 1-minute interval cron heartbeat runs
├── .env.example              # Environment variables template
├── .gitignore                # Comprehensive exclusions (.venv, caches, secrets, local DBs)
├── requirements.txt          # Production and testing dependencies
└── README.md                 # Complete documentation and verification runbook
```

---

## Troubleshooting Guide

### 1. FastAPI Not Running or Port 8000 Already in Use
- **Symptom**: `[Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000)`
- **Solution**: Terminate any lingering python/uvicorn process:
  ```powershell
  # On Windows PowerShell
  Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force
  ```
  Then restart uvicorn on port 8000.

### 2. Inngest Dev Server Cannot Connect to App
- **Symptom**: Inngest logs display `Failed to fetch apps` or `Connection refused`.
- **Solution**: Ensure FastAPI is running on `http://127.0.0.1:8000` **before** starting the Inngest Dev Server. Verify endpoint availability by curling:
  ```powershell
  curl.exe -i http://127.0.0.1:8000/api/inngest
  ```

### 3. Inngest Dashboard Unavailable at localhost:8288
- **Symptom**: Browser cannot open `http://localhost:8288`.
- **Solution**: Verify `npx inngest-cli@latest` is actively running in Terminal 2. If port 8288 is occupied, the CLI will output the alternate port it bound to.

### 4. Missing Signing Key Error
- **Symptom**: `SigningKeyMissingError` when starting FastAPI.
- **Solution**: Inngest requires no signing keys during local development. Ensure `INNGEST_ENVIRONMENT` is not set to `production` in your environment, which allows `inngest_client.py` to run in local Dev Server mode.
