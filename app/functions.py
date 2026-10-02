import datetime
import logging
import inngest
from app.inngest_client import inngest_client
from app.reports import reports_db, update_report

logger = logging.getLogger("app.functions")


@inngest_client.create_function(
    fn_id="say-hello",
    trigger=inngest.TriggerEvent(event="test/hello"),
    name="Say Hello",
)
async def say_hello(ctx: inngest.Context) -> str:
    """Stage 1 Inngest function: sleeps for 5 seconds in background and returns greeting."""
    await ctx.step.sleep("sleep-5s", datetime.timedelta(seconds=5))
    return "Hello from the background!"


@inngest_client.create_function(
    fn_id="make-report",
    trigger=inngest.TriggerEvent(event="report/requested"),
    retries=2,
    name="Make Report",
)
async def make_report(ctx: inngest.Context) -> dict:
    """Stage 2 & 3 Inngest function: 2-step workflow with retries=2 and deliberate failure trigger."""
    report_id = ctx.event.data.get("id")
    topic = ctx.event.data.get("topic")

    # Step 1: do-the-slow-work (approximately 8-second durable sleep)
    await ctx.step.sleep("do-the-slow-work", datetime.timedelta(seconds=8))

    # Step 2: build-report (generates the report result and updates store to done)
    async def _build_report():
        # Deliberately simulate transient background failure if topic == 'fail'
        if topic == "fail":
            raise Exception("The report oven is broken!")

        result = f"Summary report on '{topic}': Detailed intelligence and data analysis completed."
        update_report(report_id, status="done", result=result)
        return {
            "id": report_id,
            "topic": topic,
            "status": "done",
            "result": result,
        }

    report_result = await ctx.step.run("build-report", _build_report)
    return report_result


@inngest_client.create_function(
    fn_id="heartbeat",
    trigger=inngest.TriggerCron(cron="* * * * *"),
    name="Heartbeat",
)
async def heartbeat(ctx: inngest.Context) -> str:
    """Stage 4 Inngest scheduled function: runs on clock alone (* * * * *) and logs report metrics."""
    async def _log_summary():
        pending = sum(1 for r in reports_db.values() if r.get("status") == "pending")
        done = sum(1 for r in reports_db.values() if r.get("status") == "done")
        failed = sum(1 for r in reports_db.values() if r.get("status") == "failed")

        summary = f"Heartbeat: pending={pending} done={done} failed={failed}"
        logger.info(summary)
        print(summary, flush=True)
        return summary

    summary_result = await ctx.step.run("log-summary", _log_summary)
    return summary_result


# List of all active Inngest functions
inngest_functions = [say_hello, make_report, heartbeat]
