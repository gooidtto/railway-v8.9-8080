import importlib.util
from urllib.parse import parse_qs, urlparse

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]


def load_generate_with_env(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("CONFIG", str(tmp_path / "config.json"))
    monkeypatch.setenv("UUID", "d864cffe-5baa-4a6b-954c-b8346400068b")
    monkeypatch.setenv("PRIVATE_KEY", "private-test")
    monkeypatch.setenv("PUBLIC_KEY", "public-test")
    monkeypatch.setenv("VLESS_DECRYPTION", "decrypt-test")
    monkeypatch.setenv("VLESS_ENCRYPTION", "encrypt-test")
    monkeypatch.setenv("XRAY_TCP_PROXY_HOST", "example.proxy.rlwy.net")
    monkeypatch.setenv("XRAY_TCP_PROXY_PORT", "50192")
    monkeypatch.setenv("RAILWAY_PUBLIC_DOMAIN", "example.up.railway.app")
    monkeypatch.setenv("SHORT_ID", "50175c035ee132")
    monkeypatch.setenv("XHTTP_PATH", "/xhttp")
    monkeypatch.setenv("XHTTP_MODE", "auto")
    spec = importlib.util.spec_from_file_location("generate_under_test", ROOT / "scripts" / "generate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generated_subscription_and_client_share_material(monkeypatch, tmp_path):
    load_generate_with_env(monkeypatch, tmp_path)

    nodes = (tmp_path / "vless.txt").read_text().splitlines()
    assert len(nodes) == 2

    reality = next(url for url in nodes if "security=reality" in url)
    query = parse_qs(urlparse(reality).query)
    assert query["encryption"] == ["encrypt-test"]
    assert query["pbk"] == ["public-test"]
    assert query["sid"] == ["50175c035ee132"]
    assert query["path"] == ["/xhttp"]
    assert query["mode"] == ["auto"]

    client = __import__("json").loads((tmp_path / "client.json").read_text())
    reality_client = next(o for o in client["outbounds"] if o["streamSettings"]["security"] == "reality")
    user = reality_client["settings"]["vnext"][0]["users"][0]
    reality_settings = reality_client["streamSettings"]["realitySettings"]
    assert user["id"] == "d864cffe-5baa-4a6b-954c-b8346400068b"
    assert user["encryption"] == "encrypt-test"
    assert reality_settings["publicKey"] == "public-test"
    assert reality_settings["shortId"] == "50175c035ee132"
    assert reality_settings["serverName"] == "www.cloudflare.com"
