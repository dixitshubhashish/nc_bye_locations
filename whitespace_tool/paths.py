"""Application-owned filesystem locations."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
