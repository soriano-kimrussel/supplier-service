"""Standalone enrichment worker: `python -m app.workers.enrichment_worker`.

It is a separate process from the API so a slow model call can never make an
HTTP request wait, and so the two can be scaled independently.
"""

import asyncio
import contextlib
import logging
import signal

from anthropic import AsyncAnthropic

from app.clients import ClaudeEnricher, Enricher
from app.config import Settings, get_settings
from app.db import Database
from app.services import EnrichmentService

logger = logging.getLogger(__name__)


def build_enricher(settings: Settings) -> Enricher | None:
    """No API key means no enrichment; ingestion still works."""
    if not settings.anthropic_api_key:
        logger.warning("ANTHROPIC_API_KEY is not set - enrichment jobs will be skipped")
        return None
    return ClaudeEnricher(
        AsyncAnthropic(api_key=settings.anthropic_api_key),
        model=settings.enrichment_model,
    )


async def run(settings: Settings, stop: asyncio.Event) -> None:
    database = Database(settings.database_url, echo=settings.database_echo)
    service = EnrichmentService(
        database,
        build_enricher(settings),
        max_attempts=settings.worker_max_attempts,
    )

    logger.info("enrichment worker started")
    try:
        while not stop.is_set():
            try:
                handled = await service.run_once(settings.worker_batch_size)
            except Exception:  # a bad batch must not kill the worker
                logger.exception("enrichment batch failed")
                handled = 0

            if handled == 0:
                # Idle: wait for the poll interval, or for shutdown, whichever first.
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        stop.wait(), timeout=settings.worker_poll_interval_seconds
                    )
    finally:
        await database.dispose()
        logger.info("enrichment worker stopped")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await run(settings, stop)


if __name__ == "__main__":
    asyncio.run(main())
