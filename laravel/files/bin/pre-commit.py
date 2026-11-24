#!/usr/bin/env python3
"""Run the checksum-pinned pre-commit release. Downloads require explicit setup."""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen

VERSION = "4.7.0"
SHA256 = "393488513aed286d7a5a978a1fe79b2f5a8802927242a2d241ff10c1a8e8c885"
URL = f"https://github.com/pre-commit/pre-commit/releases/download/v{VERSION}/pre-commit-{VERSION}.pyz"


def main():
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    runner = cache / "leadbuster" / f"pre-commit-{VERSION}.pyz"
    setup = sys.argv[1:] == ["--setup"]
    if setup and not runner.exists():
        runner.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(URL, timeout=60) as response:
            payload = response.read()
        if hashlib.sha256(payload).hexdigest() != SHA256:
            raise RuntimeError("Downloaded pre-commit checksum mismatch.")
        with tempfile.NamedTemporaryFile(dir=runner.parent, delete=False) as temporary:
            temporary.write(payload)
        os.replace(temporary.name, runner)
    if not runner.is_file():
        raise RuntimeError("Run python3 bin/pre-commit.py --setup before committing.")
    if hashlib.sha256(runner.read_bytes()).hexdigest() != SHA256:
        raise RuntimeError(f"pre-commit checksum mismatch: remove {runner} and run --setup.")
    arguments = ["install-hooks"] if setup else sys.argv[1:]
    return subprocess.call([sys.executable, str(runner), *arguments])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError) as error:
        print(f"pre-commit: {error}", file=sys.stderr)
        sys.exit(1)
