import uuid
from fastapi import FastAPI, HTTPException, status
import inngest
import inngest.fast_api
import uvicorn

from app.inngest_client import inngest_client
from app.functions import inngest_functions
from app.models import CreateReportRequest, CreateReportResponse, ReportResponse
from app.reports import create_report, get_report

app = FastAPI(
    title="FlyRank Background Job Service",
    description="Background report processing and scheduled jobs with FastAPI and Inngest",
    version="1.0.0",
)


@app.get("/health")
def health_check():
    """Health check endpoint confirming server operational status."""
    return {"status": "ok"}


@app.post(
    "/reports",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateReportResponse,
)
async def request_report(request: CreateReportRequest):
    """Fast door: accepts report request, dispatches background event, returns 202 immediately."""
    report_id = str(uuid.uuid4())

    # 1. Save initial report record with pending status
    create_report(topic=request.topic, report_id=report_id)

    # 2. Trigger Inngest background event
    await inngest_client.send(
        inngest.Event(
            name="report/requested",
            data={
                "id": report_id,
                "topic": request.topic,
            },
        )
    )

    # 3. Return 202 Accepted immediately with id and pending status
    return CreateReportResponse(id=report_id, status="pending")


@app.get("/reports/{report_id}", response_model=ReportResponse)
def get_report_status(report_id: str):
    """Status endpoint: returns pending initially, and done + result once completed."""
    report = get_report(report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    return ReportResponse(**report)


# Register Inngest functions with FastAPI at /api/inngest
inngest.fast_api.serve(
    app,
    inngest_client,
    inngest_functions,
)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
