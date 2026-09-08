import httpx

from rocinante.kord import KordClient


def test_share_diff_sends_ork_as_zip(tmp_path):
    before = tmp_path / "before.ork"
    after = tmp_path / "after.ork"
    before.write_bytes(b"before")
    after.write_bytes(b"after")
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(200, json={"url": "https://example.test/d/abc"})

    client = KordClient(base_url="https://example.test")
    client._client = httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(handler)
    )
    try:
        assert client.share_diff(before, after)["url"] == "https://example.test/d/abc"
    finally:
        client.close()

    assert seen["body"].count(b"Content-Type: application/zip") == 2
