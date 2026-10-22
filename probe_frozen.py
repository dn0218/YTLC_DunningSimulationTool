# probe_frozen.py - the 3016 flag is set at IMPORT time of oracledb.thin_impl;
# spy on imports BEFORE importing oracledb to catch the swallowed failure.
import builtins
import traceback

_orig = builtins.__import__
fails = []


def spy(name, *args, **kwargs):
    try:
        return _orig(name, *args, **kwargs)
    except Exception as e:
        fails.append((name, type(e).__name__, str(e)[:300]))
        raise


print("step 1: spying while importing cryptography + oracledb ...")
builtins.__import__ = spy
try:
    import cryptography         # noqa: F401
    import oracledb             # noqa: F401
finally:
    builtins.__import__ = _orig

print("oracledb", oracledb.__version__, "imported;",
      len(fails), "failed imports during init")
for name, et, msg in fails:
    print("INIT-FAIL:", name, "->", et, msg)

# also: try the modules oracledb's thin_impl typically needs, one by one
for mod in ("cryptography.hazmat.primitives.ciphers.aead",
            "cryptography.hazmat.backends.openssl.backend",
            "cryptography.hazmat.primitives.ciphers.algorithms",
            "cryptography.hazmat.primitives.ciphers.modes"):
    try:
        __import__(mod, fromlist=["x"])
        print("PASS", mod)
    except Exception as e:
        print("FAIL", mod, "->", type(e).__name__, e)

try:
    oracledb.connect(user="x", password="y", dsn="127.0.0.1:1/INVALID")
except Exception as e:
    print("connect ->", type(e).__name__, str(e)[:160])
