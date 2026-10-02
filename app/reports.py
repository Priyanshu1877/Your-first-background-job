import uuid
from typing import Optional, Dict, Any

# In-memory store for reports: {report_id: report_data}
reports_db: Dict[str, Dict[str, Any]] = {}


def create_report(topic: str, report_id: Optional[str] = None) -> Dict[str, Any]:
    """Create and store a new report with initial 'pending' status."""
    if report_id is None:
        report_id = str(uuid.uuid4())

    report = {
        "id": report_id,
        "topic": topic,
        "status": "pending",
        "result": None,
    }
    reports_db[report_id] = report
    return report


def get_report(report_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a report by ID from the in-memory store."""
    return reports_db.get(report_id)


def update_report(
    report_id: str,
    status: str,
    result: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Update the status and result of a stored report."""
    report = reports_db.get(report_id)
    if report:
        report["status"] = status
        if result is not None:
            report["result"] = result
    return report


def clear_reports() -> None:
    """Helper to clear store for testing isolation."""
    reports_db.clear()
