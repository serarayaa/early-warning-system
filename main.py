from src.config.settings import PATHS
from src.utils.logging_utils import setup_logging, get_logger
from src.cli.args import build_parser
from src.cli.handlers import handle


def main() -> int:
    cfg = PATHS.root / "src" / "config" / "logging.yaml"
    if cfg.exists():
        setup_logging(cfg)
    log = get_logger("EWS")

    try:
        return handle(build_parser().parse_args())
    except Exception as e:
        log.exception(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())