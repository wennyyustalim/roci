import json

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


def test_large_share_preserves_before_after_identity_through_signed_uploads(
    tmp_path, monkeypatch
):
    before = tmp_path / "accepted.glb"
    after = tmp_path / "proposal.glb"
    before.write_bytes(b"accepted bytes")
    after.write_bytes(b"proposal bytes")
    uploads = []
    share_body = {}
    upload_urls = iter(
        [
            {"uploadUrl": "https://uploads.example/before", "key": "before-key"},
            {"uploadUrl": "https://uploads.example/after", "key": "after-key"},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/diff/upload-url":
            return httpx.Response(200, json=next(upload_urls))
        if request.url.path == "/api/diff/share":
            share_body.update(json.loads(request.content))
            return httpx.Response(200, json={"url": "/d/large-pair"})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    def upload(method, url, content, headers, timeout):
        uploads.append(
            {"method": method, "url": url, "content": content, "headers": headers, "timeout": timeout}
        )
        return httpx.Response(200)

    monkeypatch.setattr("rocinante.kord.client.MULTIPART_BUDGET", 1)
    monkeypatch.setattr("rocinante.kord.client.httpx.request", upload)
    client = KordClient(base_url="https://example.test")
    client._client = httpx.Client(
        base_url=client.base_url, transport=httpx.MockTransport(handler)
    )
    try:
        assert client.share_diff(before, after, title="v1 to v3", ttl_days=3) == {
            "url": "/d/large-pair"
        }
    finally:
        client.close()

    assert [item["content"] for item in uploads] == [b"accepted bytes", b"proposal bytes"]
    assert share_body == {
        "before": {"fileKey": "before-key", "fileName": "accepted.glb"},
        "after": {"fileKey": "after-key", "fileName": "proposal.glb"},
        "ttlDays": 3,
        "title": "v1 to v3",
    }
