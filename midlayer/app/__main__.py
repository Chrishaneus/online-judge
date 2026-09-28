"""Entrypoint: python -m app runs the grpc.aio JudgeService server until SIGTERM/SIGINT."""

import asyncio
import logging
import signal

from app import create_app
from app.config import Settings


async def main() -> None:
    app = create_app(Settings.from_env())
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)

    start = asyncio.create_task(app.start())
    stopped = asyncio.create_task(stop.wait())
    await asyncio.wait({start, stopped}, return_when=asyncio.FIRST_COMPLETED)
    if start.done():
        start.result()
        await stopped
    else:
        start.cancel()
    logging.getLogger("app").info("shutting down")
    await app.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    logging.getLogger("aiormq").setLevel(logging.WARNING)
    asyncio.run(main())
