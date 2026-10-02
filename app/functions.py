import datetime
import inngest
from app.inngest_client import inngest_client


@inngest_client.create_function(
    fn_id="say-hello",
    trigger=inngest.TriggerEvent(event="test/hello"),
    name="Say Hello",
)
async def say_hello(ctx: inngest.Context) -> str:
    """Stage 1 Inngest function: sleeps for 5 seconds in background and returns greeting."""
    await ctx.step.sleep("sleep-5s", datetime.timedelta(seconds=5))
    return "Hello from the background!"


# List of all active Inngest functions
inngest_functions = [say_hello]
