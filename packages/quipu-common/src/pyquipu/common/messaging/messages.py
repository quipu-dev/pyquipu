import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def find_locales_dir() -> Path | None:
    try:
        # The 'locales' directory is now part of the quipu.common package data
        locales_path = Path(__file__).parent.parent / "locales"
        if locales_path.is_dir():
            logger.debug(f"Found locales directory at: {locales_path}")
            return locales_path
    except Exception as e:
        logger.error(f"Error finding locales directory: {e}")

    logger.warning("Could not find the 'locales' directory.")
    return None
