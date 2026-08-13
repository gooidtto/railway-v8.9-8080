import os
import tempfile
from pathlib import Path

from scripts.select_reality_sni import select_sni


def test_static_mode_keeps_cloudflare():
    assert select_sni(["www.microsoft.com"], "static", "www.cloudflare.com") == "www.cloudflare.com"


def test_random_mode_uses_only_candidates():
    # Use localhost so the test does not depend on public DNS.
    assert select_sni(["localhost"], "random", "www.cloudflare.com") == "localhost"
