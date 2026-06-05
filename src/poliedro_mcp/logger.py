import logging
import os
import sys
from pathlib import Path

def get_log_dir() -> Path:
    env_dir = os.getenv("POLIEDRO_LOG_DIR")
    if env_dir:
        return Path(env_dir).expanduser()

    return Path.home() / ".poliedro-mcp" / "logs"

logger = logging.getLogger("poliedro-mcp")
logger.setLevel(logging.INFO)
logger.handlers.clear()

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)

stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setFormatter(formatter)
logger.addHandler(stderr_handler)

if os.getenv("POLIEDRO_LOG_DIR"):
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "poliedro-mcp.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info("Logger iniciado (arquivo=%s)", log_file)
else:
    logger.info("Logger iniciado (somente stderr)")

logger.propagate = False
