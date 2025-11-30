from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def find_locales_dir() -> Path | None:
    """
    Find the 'locales' directory located relative to this file.
    This is robust for both development and installed package environments.
    """
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
