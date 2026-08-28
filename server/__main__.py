"""Loopback-only launcher for the first return-integration slice."""

import argparse
import json
from pathlib import Path
import secrets

from .api import create_app
from .settings import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("server/local-config.json"))
    parser.add_argument("--init", action="store_true", help="Create fictional-user credentials without overwriting a file")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    if args.init:
        config = {
            "database": "data/returns.sqlite3",
            "citizen_tokens": {"demo-citizen": secrets.token_urlsafe(32)},
            "device_token": secrets.token_urlsafe(32),
        }
        args.config.parent.mkdir(parents=True, exist_ok=True)
        with args.config.open("x", encoding="utf-8") as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
        print(f"Created local credentials at {args.config}. Keep this file out of Git.")
        return
    import uvicorn
    uvicorn.run(create_app(Settings.from_file(args.config)), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
