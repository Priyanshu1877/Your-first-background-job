# FlyRank Backend AI Engineering — Your First Background Job

A background job processing API built with **FastAPI** and **Inngest**. Slow tasks run in durable background workflows, allowing API endpoints to respond immediately while clients poll a status endpoint to track progress.

---

## Architecture & Lifecycle Overview

When an API performs a slow operation (e.g. report compilation, AI model inference, PDF exports), holding the HTTP connection open causes slow response times, timeouts, and redundant work on retries.

This project implements the standard **Accept Fast → Work in Background → Report Status** pattern:

```
[Client] --- (1) POST /reports {"topic":"cats"} ---> [FastAPI]
[Client] <-- (2) 202 Accepted {"id":"...", "status":"pending"} (<10ms) -- [FastAPI]
                                                          |
                                           (3) Send event: report/requested
                                                          v
                                                  [Inngest Dev Server]
                                                          |
                                           (4) Step 1: do-the-slow-work (~8s sleep)
                                           (5) Step 2: build-report (updates store)
                                                          v
[Client] --- (6) GET /reports/{id} (poll) ---------> [FastAPI] -> {"status": "pending"}
                                                    ... 8-10 seconds later ...
[Client] --- (7) GET /reports/{id} (poll) ---------> [FastAPI] -> {"status": "done", "result": "..."}
```

---

## Stage 3: Retries vs. Bad Input Validation

> **"Bad input is rejected at the door; transient background failures are retried."**

### Why this distinction matters:
- **Bad Input (Rejected immediately)**: If a client submits a request without a topic (e.g. `{}`), retrying the request in the background will never fix the mistake. Invalid inputs must be caught immediately at the HTTP boundary, returning `400 Bad Request` without creating database records or dispatching queue events.
- **Transient Failures (Retried automatically)**: Once a valid request enters the background queue, network blips, database deadlocks, or external API outages may cause temporary failures. These transient failures deserve automatic retries with exponential backoff.
- **Retry Count (`retries = 2`)**: Configured on `make-report` via `retries=2`. This results in **3 total attempts**:
  1. **Attempt 1**: Initial execution fails.
  2. **Attempt 2**: First retry with backoff fails.
  3. **Attempt 3**: Second retry with backoff fails.
  4. **Final State**: Retries exhausted → Status permanently transitions to **Failed**.
- **Deliberate Failure Trigger**: When `topic == "fail"`, the `build-report` step raises `Exception("The report oven is broken!")` to demonstrate this retry lifecycle.

---

## Stage 4: Cron Heartbeat (Scheduled Workflow)

The project includes an autonomous scheduled job (`heartbeat`) that runs on the clock alone without any HTTP request or incoming event.

### Function Configuration & Schedule:
- **Function Name / ID**: `Heartbeat` (`heartbeat`)
- **Trigger**: `inngest.TriggerCron(cron="* * * * *")`
- **Testing Schedule**: Every minute (`* * * * *`)
- **Summary Log Format**:
  Reads the current in-memory report store and logs one concise summary line:
  ```
  Heartbeat: pending=0 done=2 failed=0
  ```
- **No HTTP Endpoint**: The heartbeat function has no corresponding HTTP door; it is driven entirely by the Inngest scheduler.

### Cron Expressions Explained:

A standard cron expression consists of five fields evaluated from left to right:

```
┌───────────── minute (0 - 59)
│ ┌───────────── hour (0 - 23)
│ │ ┌───────────── day of the month (1 - 31)
│ │ │ ┌───────────── month (1 - 12)
│ │ │ │ ┌───────────── day of the week (0 - 6) (0 to 6 are Sunday to Saturday)
│ │ │ │ │
* * * * *
```

1. **Every day at 08:00**:
   ```
   0 8 * * *
   ```
   - `0`: Minute 0
   - `8`: Hour 8 (08:00 AM)
   - `*`: Every day of the month
   - `*`: Every month
   - `*`: Every day of the week

2. **Every Sunday at 22:00**:
   ```
   0 22 * * 0
   ```
   - `0`: Minute 0
   - `22`: Hour 22 (10:00 PM)
   - `*`: Every day of the month
   - `*`: Every month
   - `0`: Sunday (day of week 0)

### Timezone Considerations:
Server environments and cron schedulers (including cloud workers and containers) typically evaluate cron expressions in **UTC (Coordinated Universal Time)** by default. Before relying on a production schedule, always verify the server's configured timezone and convert local business hours to UTC (or specify the timezone explicitly, e.g., `TZ=America/New_York 0 8 * * *`).

---

## Prerequisites

- **Python**: 3.10+ (tested on Python 3.14)
- **Node.js / npx**: For the Inngest local Dev Server CLI (`npx inngest-cli@latest`)

---

## Quick Start & Running the Project

### 1. Set Up Virtual Environment & Dependencies

```bash
# In the week7-background-job directory
python -m venv .venv

# On Windows:
.\.venv\Scripts\pip install -r requirements.txt

# On macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Start FastAPI Server (Terminal 1)

```bash
# Windows
.\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000

# macOS / Linux
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 3. Start Inngest Dev Server (Terminal 2)

```bash
npx inngest-cli@latest dev -u http://127.0.0.1:8000/api/inngest
```

- **Inngest Dashboard URL**: [http://localhost:8288](http://localhost:8288)

---

## API Endpoints

| Method | Endpoint | Description | Expected Status |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | Service health probe | `200 OK` |
| `GET` | `/api/inngest` | Inngest function introspection & communication endpoint | `200 OK` |
| `POST` | `/reports` | Fast door: accepts topic, dispatches background event, returns immediately (rejects missing topic with 400) | `202 Accepted` / `400 Bad Request` |
| `GET` | `/reports/{id}` | Status endpoint: returns `pending` initially, `done` + `result` after background job | `200 OK` / `404 Not Found` |

---

## Inngest Functions

| Function Name | Function ID | Trigger Event / Schedule | Retries | Steps | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Say Hello` | `say-hello` | `test/hello` | Default | 1. `sleep-5s` (5s durable sleep) | Introductory background workflow returning greeting |
| `Make Report` | `make-report` | `report/requested` | `2` (3 total attempts) | 1. `do-the-slow-work` (~8s durable sleep)<br>2. `build-report` (generates result & updates status to `done`, raises if `fail`) | Asynchronous report generator with retries and failure handling |
| `Heartbeat` | `heartbeat` | `cron: "* * * * *"` | Default | 1. `log-summary` (aggregates store metrics) | Scheduled cron job running every minute logging report metrics |

---

## Live Verification Proof

The following actual verification traces were recorded live against the local FastAPI and Inngest Dev Server:

### 1. Fast 202 Accepted (< 8 ms)
```bash
POST http://127.0.0.1:8000/reports
Content-Type: application/json
Body: {"topic": "cats"}

Status: 202 Accepted
Response Time: 7.64 ms
Response Body:
{
  "id": "27fc77eb-58cd-40a7-928a-db240f938cc1",
  "status": "pending"
}
```

### 2. Eventual Consistency Polling (Pending → Done)
```bash
# Immediate Poll (Returns Pending):
GET http://127.0.0.1:8000/reports/27fc77eb-58cd-40a7-928a-db240f938cc1
Status: 200 OK -> {"id": "27fc77eb-...", "topic": "cats", "status": "pending", "result": null}

# Second Poll (After ~9.5 Seconds — Returns Done + Result):
GET http://127.0.0.1:8000/reports/27fc77eb-58cd-40a7-928a-db240f938cc1
Status: 200 OK -> {"id": "27fc77eb-...", "topic": "cats", "status": "done", "result": "Summary report on 'cats': Detailed intelligence and data analysis completed."}
```

### 3. Bad Input Rejection (HTTP 400)
```bash
POST http://127.0.0.1:8000/reports
Content-Type: application/json
Body: {}

Status: 400 Bad Request
Response Body:
{
  "detail": "Field 'topic' is required and cannot be empty"
}
# Result: No database record created, no Inngest background event dispatched.
```

### 4. Background Retry & Final Failure (topic="fail")
```bash
POST http://127.0.0.1:8000/reports
Content-Type: application/json
Body: {"topic": "fail"}

Status: 202 Accepted
Response Body: {"id": "db1e9c05-f359-4247-a72b-cfe811092832", "status": "pending"}
```
- **Inngest Run ID**: `01M3XPDXZKF86PW6KXX14CKBPY`
- **Execution Log**:
  - `Attempt 1`: Error `"The report oven is broken!"`
  - `Retry 1 (Attempt 2)`: Error `"The report oven is broken!"`
  - `Retry 2 (Attempt 3)`: Error `"The report oven is broken!"`
  - `Final State`: **Failed** after 3 attempts with exponential backoff.

### 5. Cron Heartbeat Live Verification (`* * * * *`)
- **Observed Runs**: Consecutive ticks at `07:13:00 UTC`, `07:14:00 UTC`, `07:15:00 UTC`, `07:16:00 UTC`, `07:17:00 UTC`, and `07:18:00 UTC` (exactly 1 minute apart).
- **Logged Output**:
  ```
  Heartbeat: pending=0 done=2 failed=0
  ```
- **Screenshot Artifacts**:
  - Completed report run: [`screenshots/stage2_report_completed.png`](screenshots/stage2_report_completed.png)
  - Retry failure: [`screenshots/stage3_retry_failed.png`](screenshots/stage3_retry_failed.png)
  - Cron heartbeat runs: [`screenshots/stage4_heartbeat.png`](screenshots/stage4_heartbeat.png)

---

## Running Automated Tests

Run the full pytest suite across all stages:

```bash
.\.venv\Scripts\pytest -v
```
