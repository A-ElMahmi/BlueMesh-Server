# Run: uvicorn main:app --reload --host 0.0.0.0 --port 8000

import logging
import re
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path as FsPath
from typing import Annotated, List

from fastapi import FastAPI, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from starlette.requests import Request
from starlette.responses import Response

from db import get_connection, init_db

LOGS_DIR = FsPath(__file__).parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
_log_file = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

logging.basicConfig(
    filename=str(_log_file),
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("blessed")

APP_ID_RE = re.compile(r"^[0-9a-f]{8}$")


# --------------- models ---------------

class IncomingMessage(BaseModel):
    messageId: str = Field(..., alias="messageId")
    from_app: str = Field(..., alias="from")
    to: str
    content: str = Field(..., min_length=1)

    @field_validator("messageId")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        if not v:
            raise ValueError("messageId must not be empty")
        return v

    @field_validator("from_app", mode="before")
    @classmethod
    def validate_from(cls, v: str) -> str:
        v = v.lower()
        if not APP_ID_RE.match(v):
            raise ValueError("from must be an 8-char hex string")
        return v

    @field_validator("to")
    @classmethod
    def validate_to(cls, v: str) -> str:
        v = v.lower()
        if not APP_ID_RE.match(v):
            raise ValueError("to must be an 8-char hex string")
        return v

    model_config = {"populate_by_name": True}


class OutgoingMessage(BaseModel):
    messageId: str
    from_: str = Field(..., alias="from")
    content: str
    receivedAt: str

    model_config = {"populate_by_name": True}


# --------------- app ---------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Blessed Message Gateway", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    body = await request.body()
    log.info(">>> %s %s  body=%s", request.method, request.url.path, body.decode(errors="replace"))
    response = await call_next(request)
    chunks = [chunk async for chunk in response.body_iterator]
    resp_body = b"".join(chunks)
    log.info("<<< %s  body=%s", response.status_code, resp_body.decode(errors="replace"))
    return Response(content=resp_body, status_code=response.status_code,
                    headers=dict(response.headers), media_type=response.media_type)


# --------------- routes ---------------

AppId = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{8}$")]


@app.post("/message")
def post_message(msg: IncomingMessage):
    now_ms = int(time.time() * 1000)
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO messages (message_id, from_app_id, to_app_id, content, received_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (msg.messageId, msg.from_app, msg.to, msg.content, now_ms),
            )
    except sqlite3.IntegrityError:
        pass  # duplicate messageId — silently ignore per spec
    return {"ok": True}


@app.get("/messages/{app_id}", response_model=List[OutgoingMessage])
def get_messages(app_id: AppId):
    app_id = app_id.lower()
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, message_id, from_app_id, content, received_at "
            "FROM messages WHERE to_app_id = ?",
            (app_id,),
        ).fetchall()

        if not rows:
            return []

        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" * len(ids))
        conn.execute(f"DELETE FROM messages WHERE id IN ({placeholders})", ids)

    return [
        OutgoingMessage(
            messageId=row["message_id"],
            **{"from": row["from_app_id"]},
            content=row["content"],
            receivedAt=datetime.fromtimestamp(
                row["received_at"] / 1000, tz=timezone.utc
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        for row in rows
    ]
