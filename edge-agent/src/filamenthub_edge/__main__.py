"""FilamentHub Edge command line entrypoint."""

from __future__ import annotations

import argparse
import json
import logging
import signal
from dataclasses import replace
from threading import Event

from .cloud import FilamentHubCloud
from .config import EdgeConfig
from .errors import EdgeError
from .providers.moonraker import MoonrakerProvider
from .runtime import EdgeRuntime
from .state import StateStore


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
        help="revoke and clear an idle binding before pairing this Edge elsewhere",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        config = EdgeConfig.load()
        if args.once:
            config = replace(config, run_once=True)
        store = StateStore(config.state_path)
        state = store.load()
        cloud = FilamentHubCloud(
            config.filamenthub_url,
            timeout=config.request_timeout,
            allow_insecure_http=config.allow_insecure_cloud,
        )
        provider = MoonrakerProvider(
            config.moonraker_url,
            api_key=config.moonraker_api_key,
            material_provider=config.material_provider,
            timeout=config.request_timeout,
        )
        runtime = EdgeRuntime(
            config=config,
            cloud=cloud,
            provider=provider,
            store=store,
            state=state,
        )
        if args.status:
            print(json.dumps(runtime.diagnostic_status(), sort_keys=True))
        elif args.reset_connection:
            runtime.reset_connection()
            logging.getLogger("filamenthub_edge").info("Edge connection was reset safely")
        elif config.run_once:
            runtime.run_cycle()
        else:
            stop_event = Event()

            def request_stop(signum, frame) -> None:  # noqa: ANN001, ARG001
                logging.getLogger("filamenthub_edge").info("Edge stop requested")
                stop_event.set()

            signal.signal(signal.SIGINT, request_stop)
            signal.signal(signal.SIGTERM, request_stop)
            try:
                runtime.run_forever(stop_event=stop_event)
            finally:
                runtime.shutdown()
    except EdgeError as exc:
        logging.getLogger("filamenthub_edge").error("%s", exc)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
