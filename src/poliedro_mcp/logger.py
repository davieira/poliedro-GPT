import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("poliedro-mcp")
logger.setLevel(logging.INFO)
logger.propagate = False

if not logger.handlers:
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    logger.addHandler(stderr_handler)

    log_dir = os.getenv("POLIEDRO_LOG_DIR", "").strip()
    if log_dir:
        path = Path(log_dir).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path / "poliedro-mcp.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
