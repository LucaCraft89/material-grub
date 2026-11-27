"""The Ventoy download in the QEMU tests retries on transient errors (a CI run died on a 504)."""

import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ventoy_smoke as V  # noqa: E402


def gateway_timeout():
    return urllib.error.HTTPError("u", 504, "Gateway Timeout", {}, None)


class DownloadRetry(unittest.TestCase):
    def test_retries_then_succeeds(self):
        calls = []

        def fake(url, dest):
            calls.append(url)
            if len(calls) < 3:
                raise gateway_timeout()

        with mock.patch.object(V.urllib.request, "urlretrieve", fake), mock.patch.object(V.time, "sleep"):
            V.download("http://x", "d")
        self.assertEqual(len(calls), 3)

    def test_gives_up_with_the_last_error(self):
        boom = mock.patch.object(V.urllib.request, "urlretrieve", side_effect=gateway_timeout())
        with boom as m, mock.patch.object(V.time, "sleep"), self.assertRaises(urllib.error.HTTPError):
            V.download("http://x", "d", tries=3)
        self.assertEqual(m.call_count, 3)


if __name__ == "__main__":
    unittest.main()
