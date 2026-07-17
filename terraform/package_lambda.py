#!/usr/bin/env python3
"""Build the Lambda deployment zip (src/… layout) for Terraform."""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
OUT = Path(__file__).resolve().parent / "build" / "weather-pulse-nz.zip"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()

    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SRC.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            arcname = Path("src") / path.relative_to(SRC)
            zf.write(path, arcname.as_posix())

    digest = hashlib.sha256(OUT.read_bytes()).digest()
    print(
        json.dumps(
            {
                "path": str(OUT),
                "base64sha256": base64.b64encode(digest).decode("ascii"),
            }
        )
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover
        print(str(exc), file=sys.stderr)
        sys.exit(1)
