from typing import Optional
from pydantic import BaseModel, Field


class CreateReportRequest(BaseModel):
    """Payload for requesting a new report."""
    topic: str = Field(..., description="The subject or topic for the report")


class CreateReportResponse(BaseModel):
    """Immediate 202 Accepted response returned to client."""
    id: str = Field(..., description="Unique identifier for the report")
    status: str = Field(default="pending", description="Initial lifecycle state")


class ReportResponse(BaseModel):
    """Full report status and result representation."""
    id: str
    topic: str
    status: str
    result: Optional[str] = None
