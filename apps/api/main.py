import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import structlog

from config import settings
from routers import dashboard, grid_signals, projects, sites, supabase_views, vzev

log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("KAMA Energy API starting", debug=settings.debug)
    yield
    import supabase_client
    await supabase_client.close()
    log.info("KAMA Energy API shutting down")


app = FastAPI(
    title="KAMA Energy API",
    description="Energy monitoring platform for Swiss farms and SMEs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["https://app.kama.energy"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sites.router)
app.include_router(grid_signals.router)
app.include_router(vzev.router)
app.include_router(dashboard.router)
app.include_router(projects.router)
app.include_router(supabase_views.router)


@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


# ── SSE live feed ─────────────────────────────────────────────────────────────

@app.get("/sse/sites/{site_id}/live")
async def sse_live(site_id: str, request: Request):
    """Server-Sent Events stream — emits latest site reading every 30 seconds."""
    from db import AsyncSessionLocal
    from routers.sites import get_current
    from uuid import UUID

    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                async with AsyncSessionLocal() as db:
                    reading = await get_current(UUID(site_id), db)
                data = json.dumps(reading.model_dump(mode="json"))
                yield f"data: {data}\n\n"
            except Exception as exc:
                log.warning("SSE read error", site_id=site_id, error=str(exc))
                yield f"event: error\ndata: {str(exc)}\n\n"
            await asyncio.sleep(30)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
