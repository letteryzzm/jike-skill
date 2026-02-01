"""
python -m jike auth     — QR login, print tokens
python -m jike <cmd>    — API operations

Author: Claude Opus 4.5
"""

import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: jike <auth|feed|post|search|...>", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "auth":
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        from .auth import main as auth_main

        auth_main()
    else:
        from .client import main as client_main

        client_main()


if __name__ == "__main__":
    main()
