from fastapi import FastAPI
import inngest.fast_api
import uvicorn

from app.inngest_client import inngest_client
from app.functions import inngest_functions

app = FastAPI(
    title="FlyRank Background Job Service",
    description="Background report processing and scheduled jobs with FastAPI and Inngest",
    version="1.0.0",
)


@app.get("/health")
def health_check():
    """Health check endpoint confirming server operational status."""
    return {"status": "ok"}


# Register Inngest functions with FastAPI at /api/inngest
inngest.fast_api.serve(
    app,
    inngest_client,
    inngest_functions,
)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
