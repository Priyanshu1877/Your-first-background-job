import os
import inngest

# In development mode, Inngest connects to the local Dev Server (http://127.0.0.1:8288)
# and does not require cloud signing keys.
is_prod = os.getenv("INNGEST_ENVIRONMENT", "").lower() == "production"

inngest_client = inngest.Inngest(
    app_id="report-api",
    is_production=is_prod,
)
