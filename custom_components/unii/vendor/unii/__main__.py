import argparse
import asyncio
import logging
import sys

from . import UNiiLocal

_LOGGER = logging.getLogger(__name__)


async def main(unii):
    try:
        if not await unii.connect():
            _LOGGER.error("Failed to connect to UNii")
            return 1

        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        # Handle keyboard interrupt
        pass
    finally:
        await unii.disconnect()

    return 0


if __name__ == "__main__":
    # Read command line arguments
    argparser = argparse.ArgumentParser()

    subparsers = argparser.add_subparsers()

    local_parser = subparsers.add_parser("local")
    local_parser.add_argument("host")
    local_parser.add_argument("port", type=int)
    local_parser.add_argument("key", nargs="?")

    argparser.add_argument("--debug", dest="debugLogging", action="store_true")

    args = argparser.parse_args()

    _LOGGER.error(args)

    if args.debugLogging:
        logging.basicConfig(
            format="%(asctime)s %(levelname)-8s %(filename)s:%(lineno)d %(message)s",
            level=logging.DEBUG,
        )
    else:
        logging.basicConfig(format="%(message)s", level=logging.INFO)

    if "host" in args:
        unii = UNiiLocal(args.host, args.port, args.key)
    else:
        sys.exit(1)

    try:
        loop = asyncio.new_event_loop()
        sys.exit(asyncio.run(main(unii)))
    finally:
        loop.close()
