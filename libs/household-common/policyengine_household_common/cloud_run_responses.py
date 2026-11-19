"""HTTP responses that Cloud Run can deliver at any body size."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from flask import Response


# Cloud Run replaces a response larger than 32 MiB with HTTP 500 ("Response
# size was too large") unless the container sends it with
# ``Transfer-Encoding: chunked``: https://cloud.google.com/run/quotas
CLOUD_RUN_BUFFERED_RESPONSE_LIMIT_BYTES = 32 * 1024 * 1024
# Stream well below that limit so response headers and a body that grows
# between releases cannot push a buffered response over it.
STREAMED_RESPONSE_THRESHOLD_BYTES = 16 * 1024 * 1024
STREAMED_RESPONSE_CHUNK_BYTES = 1024 * 1024


def cloud_run_body_response(
    body: bytes,
    *,
    status: int,
    headers: Iterable[tuple[str, str]] | None = None,
    mimetype: str | None = None,
) -> Response:
    """Return ``body`` buffered when small, and chunked when large.

    Bodies up to ``STREAMED_RESPONSE_THRESHOLD_BYTES`` keep a
    ``Content-Length`` header. Larger bodies are returned from a generator,
    so Werkzeug does not compute ``Content-Length`` and Gunicorn sends them
    with ``Transfer-Encoding: chunked``, which Cloud Run does not size-limit.
    """

    response_headers = list(headers or [])
    if len(body) <= STREAMED_RESPONSE_THRESHOLD_BYTES:
        return Response(
            body,
            status=status,
            headers=response_headers,
            mimetype=mimetype,
        )
    return Response(
        _body_chunks(body),
        status=status,
        headers=response_headers,
        mimetype=mimetype,
    )


def _body_chunks(body: bytes) -> Iterator[bytes]:
    for chunk_start in range(0, len(body), STREAMED_RESPONSE_CHUNK_BYTES):
        yield body[chunk_start : chunk_start + STREAMED_RESPONSE_CHUNK_BYTES]
