#!/usr/bin/env python3
"""Launch the Vietnam-only Newsfeed API helper with an available Node.js runtime."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def main() -> int:
    candidates = [
        shutil.which("node"),
        str(
            Path.home()
            / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node"
        ),
    ]
    node = next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)
    if not node:
        print("error: Node.js is unavailable; load the Codex workspace dependencies", file=sys.stderr)
        return 2
    helper = Path(__file__).with_name("vietnam_newsfeed_api.js")
    os.execv(node, [node, str(helper), *sys.argv[1:]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
