import tomllib
from pathlib import Path

# pyproject.toml is the single source of truth for the version (see do-python-release);
# read it directly instead of hand-maintaining a copy here, which drifts.
_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

try:
    VERSION = tomllib.loads(_PYPROJECT.read_text())["project"]["version"]
except (OSError, KeyError):
    VERSION = "0.0.0"
