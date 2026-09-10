"""``scope="function"`` really does close a dependency before the response.

``app.core.database.DbSession`` relies on this to commit before the client is
told a write succeeded. That reliance is worth exactly as much as the framework
behaviour behind it, so this measures the behaviour rather than trusting the
documentation — on a pair of throwaway applications, with no database involved.

The two tests are a matched pair. The first shows the default is the *late*
stack, which is the defect; the second shows the keyword moves it. Together
they say the keyword is both necessary and sufficient, which neither says
alone — and if a future FastAPI changes either, one of them fails and names
what changed.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient


def _application(*, scope: str | None) -> tuple[FastAPI, list[str]]:
    """An app whose dependency and response body both record when they ran.

    The response is streamed so its body is produced *while it is being sent*,
    which is what makes the ordering observable: a plain response is fully
    serialized before sending, and both stacks would close after that.
    """
    events: list[str] = []

    def dependency() -> Iterator[None]:
        yield
        events.append("dependency-closed")

    depends = (
        Depends(dependency) if scope is None else Depends(dependency, scope=scope)
    )

    app = FastAPI()

    @app.get("/")
    async def endpoint(_: None = depends) -> StreamingResponse:
        def body() -> Iterator[bytes]:
            events.append("response-sent")
            yield b"ok"

        return StreamingResponse(body())

    return app, events


def test_the_default_scope_closes_the_dependency_after_the_response() -> None:
    """The defect, demonstrated.

    A ``yield`` dependency defaults to FastAPI's request-level exit stack,
    which is drained after the response has gone out. For a session dependency
    that means the ``COMMIT`` runs after the caller has been told ``201``.
    """
    app, events = _application(scope=None)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200

    assert events == ["response-sent", "dependency-closed"], (
        "FastAPI's default dependency scope has changed. Re-check whether "
        "app.core.database.DbSession still needs scope='function'."
    )


def test_function_scope_closes_the_dependency_before_the_response() -> None:
    """The fix, demonstrated.

    ``scope="function"`` moves the dependency onto the stack drained before the
    response is sent, so a commit is durable by the time the client hears about
    it — and a client that reads back immediately cannot race it.
    """
    app, events = _application(scope="function")
    with TestClient(app) as client:
        assert client.get("/").status_code == 200

    assert events == ["dependency-closed", "response-sent"], (
        "scope='function' no longer closes a dependency before the response is "
        "sent. app.core.database.DbSession depends on it doing so."
    )
