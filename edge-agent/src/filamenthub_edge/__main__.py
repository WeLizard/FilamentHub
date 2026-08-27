"""FilamentHub Edge command line entrypoint."""

from __future__ import annotations

import argparse
import logging
from dataclasses import replace

from .cloud import FilamentHubCloud
from .config import EdgeConfig
from .errors import EdgeError
from .providers.moonraker import MoonrakerProvider
from .runtime import EdgeRuntime
from .state import StateStore


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FilamentHub Edge runtime")
    parser.add_argument("--once", action="store_true", help="run one synchronization cycle")
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
        if config.run_once:
            runtime.run_cycle()
        else:
            runtime.run_forever()
    except EdgeError as exc:
        logging.getLogger("filamenthub_edge").error("%s", exc)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        raise SystemExit(0) from None


if __name__ == "__main__":
    main()
