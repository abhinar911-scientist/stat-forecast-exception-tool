#!/usr/bin/env python3
"""Generate a bcrypt hash for a user password.

    python scripts/hash_password.py              # prompts, hides input
    python scripts/hash_password.py "mypassword" # one-shot

Paste the printed hash into secrets.toml under [auth.users.<username>].
"""
import getpass
import sys

import bcrypt


def main() -> None:
    password = sys.argv[1] if len(sys.argv) > 1 else getpass.getpass("Password: ")
    if not password:
        sys.exit("No password supplied.")
    print(bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode())


if __name__ == "__main__":
    main()
