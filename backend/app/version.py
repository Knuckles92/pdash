"""Application version (from package metadata)."""

from importlib.metadata import PackageNotFoundError, version

_PKG = "pdash-backend"
_FALLBACK = "0.1.0"


def app_version() -> str:
    try:
        return version(_PKG)
    except PackageNotFoundError:
        return _FALLBACK
