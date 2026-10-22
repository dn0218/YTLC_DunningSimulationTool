# -*- coding: utf-8 -*-
"""
encrypt_config.py - encrypt / decrypt the password fields of a config.json
in place, using the ENC1 scheme from dunning_tool.config_loader.

Usage:
    python encrypt_config.py                 # encrypt ./config.json
    python encrypt_config.py path/to/json    # encrypt a specific file
    python encrypt_config.py --decrypt       # back to plain text
    python encrypt_config.py --decrypt file  # decrypt a specific file

Every "password" key inside the db / ssh / api sections is converted to
'ENC1:<base64>' (or back). Plain values are encrypted, ENC1 values are
skipped when encrypting (idempotent). The app accepts both forms, so this
tool is safe to run at any time.
"""

import argparse
import json
import os
import sys

from dunning_tool.config_loader import decrypt_text, encrypt_text

SECRET_KEYS = ("password",)
SECTIONS = ("db", "ssh", "api")


def transform(path, decrypt=False):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise SystemExit("%s: not a JSON object" % path)

    changed = []
    for section in SECTIONS:
        block = data.get(section)
        if not isinstance(block, dict):
            continue
        for key in SECRET_KEYS:
            val = block.get(key)
            if not isinstance(val, str) or not val:
                continue
            if decrypt:
                if val.startswith("ENC1:"):
                    block[key] = decrypt_text(val)
                    changed.append("%s.%s" % (section, key))
            else:
                if not val.startswith("ENC1:"):
                    block[key] = encrypt_text(val)
                    changed.append("%s.%s" % (section, key))

    if not changed:
        print("%s: nothing to %s" % (path, "decrypt" if decrypt
                                     else "encrypt"))
        return 0
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=4, ensure_ascii=False)
        fh.write("\n")
    print("%s: %s %s" % (path, "decrypted" if decrypt else "encrypted",
                         ", ".join(changed)))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Encrypt/decrypt config.json passwords (ENC1 scheme).")
    parser.add_argument("file", nargs="?", default="config.json",
                        help="config file (default: ./config.json)")
    parser.add_argument("--decrypt", action="store_true",
                        help="convert ENC1 values back to plain text")
    args = parser.parse_args()

    if not os.path.exists(args.file):
        raise SystemExit("file not found: %s" % args.file)
    return transform(args.file, decrypt=args.decrypt)


if __name__ == "__main__":
    sys.exit(main())
