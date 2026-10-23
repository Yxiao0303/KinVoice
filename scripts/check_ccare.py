"""Run the unit/integration suite with outbound HTTP transports forbidden."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


async def no_network(*args, **kwargs):
    raise AssertionError("Network calls are forbidden in C-CARE offline tests")


def main():
    suite = unittest.defaultTestLoader.discover(str(ROOT / "backend/tests"))
    with patch("httpx.AsyncHTTPTransport.handle_async_request", new=no_network), \
         patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("Network calls forbidden")):
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
