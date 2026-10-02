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
| `POST` | `/reports` | Fast door: accepts topic, dispatches background event, returns immediately | `202 Accepted` |
| `GET` | `/reports/{id}` | Status endpoint: returns `pending` initially, `done` + `result` after background job | `200 OK` / `404 Not Found` |

---

## Inngest Functions

| Function Name | Function ID | Trigger Event / Schedule | Steps | Description |
| :--- | :--- | :--- | :--- | :--- |
| `Say Hello` | `say-hello` | `test/hello` | 1. `sleep-5s` (5s durable sleep) | Introductory background workflow returning greeting |
| `Make Report` | `make-report` | `report/requested` | 1. `do-the-slow-work` (~8s durable sleep)<br>2. `build-report` (generates result & updates status to `done`) | Asynchronous report generator that offloads slow work from HTTP request |

---

## Live Verification Proof: Fast 202 & Eventual Consistency Polling

The following actual verification trace was recorded live against the local FastAPI and Inngest Dev Server:

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

### 2. Immediate Poll (Returns Pending)
```bash
GET http://127.0.0.1:8000/reports/27fc77eb-58cd-40a7-928a-db240f938cc1

Status: 200 OK
Response Body:
{
  "id": "27fc77eb-58cd-40a7-928a-db240f938cc1",
  "topic": "cats",
  "status": "pending",
  "result": null
}
```

### 3. Second Poll (After ~9.5 Seconds — Returns Done + Result)
```bash
GET http://127.0.0.1:8000/reports/27fc77eb-58cd-40a7-928a-db240f938cc1

Status: 200 OK
Response Body:
{
  "id": "27fc77eb-58cd-40a7-928a-db240f938cc1",
  "topic": "cats",
  "status": "done",
  "result": "Summary report on 'cats': Detailed intelligence and data analysis completed."
}
```

### 4. Inngest Dashboard Evidence
Inngest dashboard verification for run `01M3XNP94JGSGJAJ7QG6W5EVHZ`:
- **Function**: `Make Report` (`make-report`)
- **Trigger**: `report/requested`
- **Total Duration**: `8.159s`
- **Steps**:
  - `do-the-slow-work`: duration `8.000s`
  - `build-report`: duration `4ms`
- **Screenshot Artifact**: [`screenshots/stage2_report_completed.png`](screenshots/stage2_report_completed.png)

---

## Running Automated Tests

Run the test suite across all implemented stages:

```bash
.\.venv\Scripts\pytest -v
```
