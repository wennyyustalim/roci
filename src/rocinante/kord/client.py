"""Client for Kord, the engineering-file version control platform.

Kord is a separate, pre-existing product. Nothing in this file is a change to
it -- every route below already ships in production. This module is the
hackathon side of the integration.

THREE PATHS, IN THE ORDER YOU SHOULD REACH FOR THEM:

1. `share_diff()` -- anonymous. POST two files to `/api/diff/share`, get back a
   `/d/<token>` URL rendering Kord's real 3D diff of them: heat map, overlay,
   side-by-side, part tree. No account, no token, no Kord change. `.glb` is an
   accepted format there, so regenerated `.glb` hulls and `.ork` torpedoes are
   each one HTTP call away from a shareable, live comparison. THIS IS THE DEMO
   PATH. Keep it working.

2. `sign_in()` + `upload_version()` / `open_review_session()` -- authenticated.
   Kord's REST API is cookie-session only (`lib/api/with-auth.ts`); there is no
   bearer-token path, so an `Authorization: Bearer` header gets a 401 on every
   route. What does work is `/api/auth/demo-login`, the production password
   endpoint, gated by the DEMO_LOGIN_EMAILS allowlist. Add the demo account to
   that env var and httpx's cookie jar carries the session from there.

3. The hosted MCP server at mcp.withkord.com -- OAuth 2.1, and deliberately
   cannot write file bytes. Right for an interactive agent, wrong for a CLI
   that needs to upload a mesh. Not used here.

Every method degrades to a no-op or a local path when unconfigured, so the
design loop runs offline.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

PUBLIC_BASE = "https://work.withkord.com"

# /api/diff/share takes multipart bodies up to roughly 4 MB for both files
# together -- the platform rejects a bigger one at the edge, before Kord's code
# runs. Past that, go through the signed-upload path instead.
MULTIPART_BUDGET = 3_500_000


def _content_type(path: Path) -> str:
    """Return Kord's declared MIME type for formats it dispatches by MIME."""
    if path.suffix.lower() == ".ork":
        return "application/zip"
    return "application/octet-stream"


class KordError(RuntimeError):
    pass


class KordClient:
    def __init__(
        self,
        base_url: str | None = None,
        project_id: str | None = None,
        folder_id: str | None = None,
        email: str | None = None,
        password: str | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("KORD_API_BASE") or PUBLIC_BASE).rstrip("/")
        self.project_id = project_id or os.getenv("KORD_PROJECT_ID", "")
        self.folder_id = folder_id or os.getenv("KORD_FOLDER_ID", "")
        self.email = email or os.getenv("KORD_EMAIL", "")
        self.password = password or os.getenv("KORD_PASSWORD", "")
        self._client: httpx.Client | None = None
        self._signed_in = False

    @property
    def http(self) -> httpx.Client:
        if self._client is None:
            # cookies=... is the point: the session Kord mints has to survive
            # from sign-in through upload and review-session creation.
            self._client = httpx.Client(
                base_url=self.base_url, timeout=120, follow_redirects=True
            )
        return self._client

    @property
    def can_share(self) -> bool:
        """Anonymous diff shares need nothing but a reachable Kord."""
        return bool(self.base_url)

    def reachable(self, timeout: float = 20.0) -> bool:
        """Is this Kord answering? Ask for the comparison UI, which also warms it.

        Worth checking before the demo opens a window onto it: a local Kord is
        frequently just not started yet, and the generous timeout is for a dev
        server compiling the route on its first request.
        """
        try:
            return not self.http.get("/diff", timeout=timeout).is_error
        except httpx.HTTPError:
            return False

    @property
    def enabled(self) -> bool:
        """Authenticated writes need an allowlisted account and a folder."""
        return bool(self.base_url and self.email and self.password and self.folder_id)

    # --- 1. anonymous diff shares ----------------------------------------

    def share_diff(
        self,
        before: str | Path,
        after: str | Path,
        title: str | None = None,
        ttl_days: int = 7,
    ) -> dict:
        """Mint a public Kord diff link for two files. Returns the API payload.

        `before` and `after` are any two files Kord can render -- for us, two
        `.glb` hulls or two `.ork` OpenRocket torpedoes. Kord dispatches ORK
        by its `application/zip` MIME type, so do not let httpx default it to
        `application/octet-stream`.
        """
        before, after = Path(before), Path(after)
        for path in (before, after):
            if not path.exists():
                raise KordError(f"no such file: {path}")

        total = before.stat().st_size + after.stat().st_size
        if total > MULTIPART_BUDGET:
            return self._share_via_signed_upload(before, after, title, ttl_days)

        data = {"ttlDays": str(ttl_days)}
        if title:
            data["title"] = title
        with before.open("rb") as fa, after.open("rb") as fb:
            resp = self.http.post(
                "/api/diff/share",
                files={
                    "before": (before.name, fa, _content_type(before)),
                    "after": (after.name, fb, _content_type(after)),
                },
                data=data,
            )
        return self._json(resp, "diff share")

    def _share_via_signed_upload(
        self, before: Path, after: Path, title: str | None, ttl_days: int
    ) -> dict:
        """The two-step path: sign an upload URL per side, PUT the bytes, mint.

        Needed above ~4 MB, which a detailed hull will exceed. Same endpoint
        family, same anonymity.
        """
        refs = {}
        for side, path in (("before", before), ("after", after)):
            signed = self._json(
                self.http.post(
                    "/api/diff/upload-url",
                    json={"fileName": path.name, "size": path.stat().st_size},
                ),
                "upload url",
            )
            put = httpx.request(
                signed.get("method", "PUT"),
                signed["uploadUrl"],
                content=path.read_bytes(),
                headers={"content-type": _content_type(path)},
                timeout=180,
            )
            if put.is_error:
                raise KordError(f"upload of {path.name} failed: {put.status_code}")
            refs[side] = {"fileKey": signed["key"], "fileName": path.name}

        body = {**refs, "ttlDays": ttl_days}
        if title:
            body["title"] = title
        return self._json(self.http.post("/api/diff/share", json=body), "diff share")

    # --- 2. authenticated: versions and review sessions -------------------

    def sign_in(self) -> bool:
        """Exchange the demo credentials for a session cookie. Idempotent."""
        if self._signed_in:
            return True
        if not (self.email and self.password):
            return False
        resp = self.http.post(
            "/api/auth/demo-login", json={"email": self.email, "password": self.password}
        )
        if resp.is_error:
            raise KordError(
                f"sign-in failed: {resp.status_code} {resp.text[:200]}. "
                "Is this address in Kord's DEMO_LOGIN_EMAILS allowlist?"
            )
        self._signed_in = True
        return True

    def upload_version(self, path: str | Path, note: str = "") -> dict:
        """Upload `path` into the configured folder.

        IMPORTANT, and confirmed against a running Kord: when the bytes are a
        change to a file that already exists, this route OPENS THE REVIEW
        SESSION ITSELF and answers

            {"status": "review_session", "message": ..., "reviewSessionId": ...}

        so there is nothing to create afterwards. A first upload of a new name
        answers with the file instead. Read the session id back with
        `review_session_id_from()`; do not call `open_review_session` on the
        result, which would open a second, empty review pass.
        """
        if not self.enabled:
            return {"skipped": True}
        self.sign_in()
        path = Path(path)
        with path.open("rb") as fh:
            resp = self.http.post(
                f"/api/folders/{self.folder_id}/upload",
                files={"file": (path.name, fh)},
                data={"note": note},
            )
        return self._json(resp, "upload")

    @staticmethod
    def review_session_id_from(uploaded: dict) -> str | None:
        """The session the upload already opened, if it opened one."""
        return uploaded.get("reviewSessionId") or uploaded.get("review_session_id")

    def open_review_session(self, file_id: str) -> dict:
        """Open a review-only pass on an existing file, changing no bytes.

        Only for a file that is already there and is NOT being revised --
        a markup pass. The refit path does not use this: uploading the new
        hull is the proposal, and that route opens the session.

        NOTE: there is no `POST /api/review-sessions` collection route; a
        review session is always created against a file.
        """
        if not self.enabled or not file_id:
            return {"skipped": True, "id": None}
        self.sign_in()
        return self._json(
            self.http.post(f"/api/files/{file_id}/review-session"), "review session"
        )

    def comment(self, review_session_id: str, body: str) -> dict:
        """Attach the model's reasoning to the session a human will read."""
        if not self.enabled or not review_session_id:
            return {"skipped": True}
        self.sign_in()
        return self._json(
            self.http.post(
                f"/api/review-sessions/{review_session_id}/comments", json={"body": body}
            ),
            "comment",
        )

    def verdict(self, review_session_id: str) -> str:
        """'approved' | 'rejected' | 'pending'. The refit loop waits on this."""
        if not self.enabled or not review_session_id:
            return "approved"
        self.sign_in()
        data = self._json(
            self.http.get(f"/api/review-sessions/{review_session_id}"), "status"
        )
        return data.get("status", "pending")

    # --- plumbing ---------------------------------------------------------

    @staticmethod
    def _json(resp: httpx.Response, what: str) -> dict:
        if resp.is_error:
            raise KordError(f"{what} failed: {resp.status_code} {resp.text[:300]}")
        return resp.json()

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
