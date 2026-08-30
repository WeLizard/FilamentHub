"""FilamentHub Edge command line entrypoint."""

from __future__ import annotations

import argparse
import json
import logging
import signal
from collections.abc import Callable
from dataclasses import replace
from threading import Event

from .config import NodeConfig
from .errors import EdgeError
from .node import EdgeNode
from .storage import NodeLease


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FilamentHub Edge runtime")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="run one synchronization cycle")
    mode.add_argument(
        "--status",
        action="store_true",
        help="print secret-free local synchronization status",
    )
    mode.add_argument(
        "--reset-connection",
        action="store_true",
        help="revoke and clear the selected idle printer connection",
    )
    parser.add_argument("--connection", help="connection id for status or reset")
    return parser


def main(*, config_loader: Callable[[], NodeConfig] = NodeConfig.load) -> None:
    parser = _parser()
    args = parser.parse_args()
    if args.reset_connection and not args.connection:
        parser.error("--reset-connection requires --connection ID")
    if args.connection and not (args.status or args.reset_connection):
        parser.error("--connection is only supported with --status or --reset-connection")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        config = config_loader()
        if args.once:
            config = replace(config, run_once=True)
        if args.status:
            print(
                json.dumps(
                    EdgeNode(config).diagnostic_status(connection_id=args.connection),
                    sort_keys=True,
                )
            )
            return
        with NodeLease(config.state_directory):
            node = EdgeNode(config)
            if args.reset_connection:
                node.reset_connection(args.connection)
                logging.getLogger("filamenthub_edge").info("Edge connection was reset safely")
                return
            node.initialize()
            logging.getLogger("filamenthub_edge").info(
                "Edge node ready with %d configured connections", len(config.connections)
            )
            if config.run_once:
                success = node.run_once()
                print(json.dumps(node.diagnostic_status(), sort_keys=True))
                if not success:
                    raise SystemExit(2)
                return
            stop_event = Event()

            def request_stop(signum, frame) -> None:  # noqa: ANN001, ARG001
                logging.getLogger("filamenthub_edge").info("Edge stop requested")
                stop_event.set()

            signal.signal(signal.SIGINT, request_stop)
            signal.signal(signal.SIGTERM, request_stop)
            node.run_forever(stop_event)
    except EdgeError as exc:
        logging.getLogger("filamenthub_edge").error("%s", exc)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
