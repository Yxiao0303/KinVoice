"""Progress only until the checked final response; no raw model token streaming."""
import asyncio
import json

import anyio
from starlette.responses import StreamingResponse

from .provider import ProviderUnavailable


class TurnStreamResponse(StreamingResponse):
    def __init__(self, engine, request, authorized, release):
        self.release = release
        super().__init__(self.events(engine, request, authorized),
                         media_type="application/x-ndjson",
                         headers={"X-Accel-Buffering": "no"})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Starlette can cancel while sending a yielded event. Explicitly close
            # the generator as well as its worker before releasing the account slot.
            with anyio.CancelScope(shield=True):
                try:
                    await self.body_iterator.aclose()
                finally:
                    self.release()

    @staticmethod
    async def events(engine, request, authorized):
        queue = asyncio.Queue(maxsize=32)  # <= 5 calls, two events each, plus control events
        sequence = 0

        async def run():
            try:
                result = await engine.respond(request, on_event=queue.put_nowait)
                if await authorized():
                    queue.put_nowait({"type": "result", "result": result.model_dump()})
                else:
                    queue.put_nowait({"type": "error", "code": "session_expired"})
            except ProviderUnavailable:
                queue.put_nowait({"type": "error", "code": "model_unavailable"})
            except Exception:
                # Never send upstream exception bodies or private text to the browser.
                queue.put_nowait({"type": "error", "code": "processing_failed"})
            finally:
                queue.put_nowait(None)

        worker = asyncio.create_task(run())
        try:
            event = {"type": "start", "protocol": "ccare-stream-v1"}
            while event is not None:
                sequence += 1
                yield json.dumps({"sequence": sequence, **event}, ensure_ascii=False) + "\n"
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=8)
                except TimeoutError:
                    event = {"type": "heartbeat"}
        finally:
            worker.cancel()
            with anyio.CancelScope(shield=True):
                await asyncio.gather(worker, return_exceptions=True)
