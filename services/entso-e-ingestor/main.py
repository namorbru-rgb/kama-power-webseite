"""Entrypoint for the ENTSO-E ingestor service."""
import asyncio
import signal

import structlog

from client import EntsoEClient
from influx_writer import InfluxWriter
from poller import Poller
from producer import GridProducer

log = structlog.get_logger()


async def main() -> None:
    log.info("entso_e_ingestor_starting")

    client = EntsoEClient()
    producer = GridProducer()
    writer = InfluxWriter()

    await producer.start()

    poller = Poller(client=client, producer=producer, writer=writer)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("shutdown_signal_received")
        stop_event.set()

    loop.add_signal_handler(signal.SIGTERM, _handle_signal)
    loop.add_signal_handler(signal.SIGINT, _handle_signal)

    poll_task = asyncio.create_task(poller.run())
    await stop_event.wait()

    poll_task.cancel()
    try:
        await poll_task
    except asyncio.CancelledError:
        pass

    await producer.stop()
    writer.close()
    log.info("entso_e_ingestor_stopped")


if __name__ == "__main__":
    asyncio.run(main())
