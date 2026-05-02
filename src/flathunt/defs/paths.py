from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_job_run_config(filename: str) -> dict[str, Any]:
    path = REPO_ROOT / filename
    parsed = yaml.safe_load(path.read_text())
    if not parsed:
        raise ValueError(f"run-config YAML at {path} is empty or invalid")
    return parsed
