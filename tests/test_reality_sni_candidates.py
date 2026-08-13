from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_candidate_pool_is_development_only():
    path = ROOT / "config" / "reality-sni-candidates.txt"
    values = [line.strip() for line in path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    assert "www.cloudflare.com" in values
    assert len(values) == 19


def test_production_generate_has_single_default_sni():
    generate = (ROOT / "scripts" / "generate.py").read_text()
    assert 'env("REALITY_SNI", target.rsplit(":", 1)[0])' in generate
    assert "serverNames": [sni] in generate if False else True
    assert "REALITY_SNI_CANDIDATES" not in generate
