"""Run host-side tests against real local services without changing the caller's environment."""

import argparse
import os

# Fixed pytest child process; no shell command execution.
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=root / ".env")
    parser.add_argument("--integration-only", action="store_true")
    args = parser.parse_args()
    env_file = args.env_file.resolve()
    if not env_file.is_file():
        parser.error("Create a local .env with service URLs, or select a file with --env-file")

    parent = root / ".tools" / "pytest-runs"
    parent.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    # pytest owns only this fresh, non-existing child; existing temp directories are untouched.
    command = [
        sys.executable,
        "-m",
        "pytest",
        str(root / "tests"),
        "-q",
        "--service-env-file",
        str(env_file),
        "--basetemp",
        str(run_dir / "tmp"),
        "-o",
        f"cache_dir={run_dir / 'cache'}",
    ]
    if args.integration_only:
        command.extend(["-m", "integration"])
    environment = dict(os.environ)
    environment.update(RUN_SERVICE_TESTS="1", APP_ENVIRONMENT="test")
    print("Running host tests with real PostgreSQL/Redis integration enabled.", flush=True)
    print(f"Isolated test artifacts: {run_dir}", flush=True)
    # Fixed interpreter/module with list argv; no untrusted shell command.
    return subprocess.run(  # nosec B603
        command, cwd=root, env=environment, check=False, shell=False
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
