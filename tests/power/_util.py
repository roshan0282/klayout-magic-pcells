"""Helpers for the sky130_power tests."""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = os.path.join(REPO, "python")
sys.path.insert(0, PY)
os.environ.setdefault("KMP_PDKS", "sky130A")
# Never touch the user's cache: one temporary cache per test run.
if "KMP_CACHE_DIR" not in os.environ:
    _CACHE = tempfile.mkdtemp(prefix="hw_test_cache_")
    os.environ["KMP_CACHE_DIR"] = _CACHE

try:
    import klayout.db as db  # noqa: F401
    HAVE_KLAYOUT = True
except ImportError:  # pragma: no cover
    db = None
    HAVE_KLAYOUT = False

PDK_ROOT = os.environ.get("PDK_ROOT", "/foss/pdks")
HAVE_MAGIC = HAVE_KLAYOUT and shutil.which("magic") is not None and os.path.isdir(
    os.path.join(PDK_ROOT, "sky130A", "libs.tech", "magic"))

needs_magic = unittest.skipUnless(HAVE_MAGIC, "needs klayout, Magic and sky130A")
needs_klayout = unittest.skipUnless(HAVE_KLAYOUT, "the klayout Python module is not installed")

PRELUDE = """
import json, os, sys
sys.path.insert(0, %r)
sys.path.insert(0, %r)
import klayout.db as db
import klayout_power_pcells as kpp
""" % (PY, REPO)


def env(cache_dir, **kw):
    e = dict(os.environ, KMP_PDKS="sky130A", KMP_CACHE_DIR=cache_dir, PYTHONPATH=PY)
    e.update({k: str(v) for k, v in kw.items()})
    return e


def run_py(body, environ, args=(), timeout=600):
    """Run ``body`` (after PRELUDE) in a new Python process; (rc, output)."""
    src = PRELUDE + textwrap.dedent(body)
    p = subprocess.run([sys.executable, "-c", src] + list(args), stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, env=environ, timeout=timeout)
    return p.returncode, p.stdout.decode(errors="replace")


def cli(environ, *args, timeout=600):
    p = subprocess.run([sys.executable, "-m", "klayout_power_pcells"] + list(args),
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=environ, timeout=timeout)
    return p.returncode, p.stdout.decode(errors="replace")


def lines(text, prefix):
    """The JSON payloads of output lines starting with ``prefix``."""
    import json
    return [json.loads(ln[len(prefix):]) for ln in text.splitlines() if ln.startswith(prefix)]
