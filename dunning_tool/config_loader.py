# -*- coding: utf-8 -*-
"""
config_loader.py - loads config.json.

Search order:
    1. <exe dir>/config.json      (PyInstaller one-file build)
    2. <module dir>/config.json   (running from source)
    3. <cwd>/config.json

If missing, a default template is written next to the executable and a
ConfigError is raised so the caller can inform the user.

Passwords may be stored obfuscated with the ENC1: scheme (see encrypt_text
below); plain-text passwords keep working, so old config files are still
accepted.  Use encrypt_config.py to convert a config.json in place.
"""

import base64
import json
import os
import sys

DEFAULT_CONFIG = {
    "general": {
        "poll_interval": 3,
        "max_wait": 60,
        "b_state_retries": 3,
        "b_state_interval": 10,
        "post_trigger_wait": 10,
        "restore_wait": 5,
        "settle_wait": 4
    },
    "db": {
        "host": "YOUR_DB_HOST",
        "port": 11521,
        "service_name": "cc",
        "user": "cc",
        "password": "CHANGE_ME"
    },
    "ssh": {
        "host": "YOUR_SSH_HOST",
        "port": 22,
        "username": "CHANGE_ME",
        "password": "CHANGE_ME",
        "connect_timeout": 15,
        "command_timeout": 60,
        "retries": 3
    },
    "api": {
        "base_url": "http://YOUR_API_HOST:7000",
        "timeout": 30,
        "retries": 3
    }
}


# ----------------------------------------------------------------------
# ENC1: simple text obfuscation for passwords in config.json.
#
# This is deliberately NOT real cryptography - it is a fixed-key XOR +
# base64 "scramble" so that passwords are not readable at a glance in the
# file (shoulder surfing, screenshots, grep). Anyone with the tool source
# can decode it; for real secrecy use an OS keyring / vault instead.
# ----------------------------------------------------------------------
_ENC_PREFIX = "ENC1:"
_XOR_KEY = b"DunningTool_v4::config::obfuscation::v1"
_SECRET_KEYS = ("password",)


def encrypt_text(plain_text):
    """Obfuscate a plain-text secret as 'ENC1:<base64-xor>'."""
    data = str(plain_text).encode("utf-8")
    xored = bytes(b ^ _XOR_KEY[i % len(_XOR_KEY)]
                  for i, b in enumerate(data))
    return _ENC_PREFIX + base64.b64encode(xored).decode("ascii")


def decrypt_text(value):
    """Reverse encrypt_text. Plain values are returned unchanged."""
    if not isinstance(value, str) or not value.startswith(_ENC_PREFIX):
        return value
    xored = base64.b64decode(value[len(_ENC_PREFIX):].encode("ascii"))
    data = bytes(b ^ _XOR_KEY[i % len(_XOR_KEY)]
                 for i, b in enumerate(xored))
    return data.decode("utf-8")


def _decrypt_secrets(config):
    """Decode every ENC1: secret in-place inside a merged config dict."""
    for section_name in ("db", "ssh", "api"):
        section = config.get(section_name)
        if not isinstance(section, dict):
            continue
        for key in _SECRET_KEYS:
            val = section.get(key)
            if isinstance(val, str) and val.startswith(_ENC_PREFIX):
                section[key] = decrypt_text(val)
    return config


class ConfigError(Exception):
    """Raised when config.json is missing or invalid."""


class ConfigLoader:
    """Loads and validates config.json."""

    def __init__(self, path=None):
        self.path = path or self.find_config_path()
        self.data = None

    # ------------------------------------------------------------------
    @staticmethod
    def base_dir():
        """Directory of the executable (frozen) or of this module."""
        if getattr(sys, "frozen", False):  # PyInstaller
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    @classmethod
    def find_config_path(cls):
        candidates = [
            os.path.join(cls.base_dir(), "config.json"),
            os.path.join(os.getcwd(), "config.json"),
        ]
        for cand in candidates:
            if os.path.exists(cand):
                return cand
        return candidates[0]

    # ------------------------------------------------------------------
    def load(self, create_if_missing=True):
        if not os.path.exists(self.path):
            if not create_if_missing:
                raise ConfigError("config.json not found at %s" % self.path)
            self._write_default()
            raise ConfigError(
                "Default config.json created at %s - please edit it with the "
                "correct credentials and restart the application." % self.path
            )
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise ConfigError("Failed to read config.json: %s" % exc)

        if not isinstance(data, dict):
            raise ConfigError("config.json must contain a JSON object")

        # Merge defaults so that missing optional keys never crash the app.
        merged = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
        for section in ("db", "ssh", "api", "general"):
            user_section = data.get(section)
            if isinstance(user_section, dict):
                merged[section].update(user_section)

        # Decode ENC1-obfuscated passwords (plain values pass through).
        try:
            _decrypt_secrets(merged)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ConfigError(
                "config.json contains a malformed ENC1 value: %s "
                "(re-create the file or run encrypt_config.py --decrypt)"
                % exc)
        self.data = merged
        return merged

    # ------------------------------------------------------------------
    def _write_default(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(DEFAULT_CONFIG, fh, indent=4, ensure_ascii=False)
        except OSError:
            pass

    # ------------------------------------------------------------------
    def get(self, section, key, default=None):
        if self.data is None:
            return default
        return self.data.get(section, {}).get(key, default)

    @property
    def db(self):
        return self.data["db"]

    @property
    def ssh(self):
        return self.data["ssh"]

    @property
    def api(self):
        return self.data["api"]

    @property
    def general(self):
        return self.data["general"]
