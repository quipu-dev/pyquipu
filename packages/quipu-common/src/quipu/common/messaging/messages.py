from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def find_locales_dir() -> Path | None:
    """
    Find the 'locales' directory, searching upwards from this file.
    This allows finding the directory both in development (monorepo root)
    and in installed environments (site-packages).
    """
    current = Path(__file__).resolve()
    # In a monorepo dev setup, it's at the project root.
    for parent in [current] + list(current.parents):
        locales_path = parent / "locales"
        if locales_path.is_dir():
            logger.debug(f"Found locales directory at: {locales_path}")
            return locales_path

    logger.warning("Could not find the 'locales' directory.")
    return None
