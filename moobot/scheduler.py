from functools import cache

from apscheduler.schedulers.asyncio import AsyncIOScheduler


@cache
def get_async_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.start()
    return scheduler
