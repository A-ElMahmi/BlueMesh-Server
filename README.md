# BlueMesh Server

HTTP API for **BlueMesh**, a hybrid Bluetooth mesh / internet messaging system. This service stores messages for devices that reach it over the internet: direct inbox polling for online recipients, plus a small relay flow for offline BLE-only targets via bridge devices.

**Android app (Kotlin):** [github.com/A-ElMahmi/BlueMesh](https://github.com/A-ElMahmi/BlueMesh)

**Deployed API base URL:** [https://bluemesh-server.onrender.com](https://bluemesh-server.onrender.com)

Default Git branch: `master`.


## Stack

- **Python 3.10+** (tested with 3.10.7)
- **FastAPI** + **Uvicorn**
- **SQLite** (`bluemesh.db` in the project root, created on first run)


## Configuration

1. Copy `.env.example` to `.env` in the project root.
2. Set `**BLUEMESH_API_KEY`** to a long random secret (do not commit real values; `.env` is gitignored).
3. The mobile app must send that same value on every API request as header `**X-API-Key**`. Missing or wrong key → **401**; if the server has no key configured → **500**.


## Local setup

```bash
git clone -b master https://github.com/A-ElMahmi/BlueMesh-Server.git
cd BlueMesh-Server
python -m venv .venv
```

Activate the venv, then:

```bash
pip install -r requirements.txt
```

Create `.env` as above, then run:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Interactive docs** (when the server is running): `http://127.0.0.1:8000/docs` (Swagger UI). OpenAPI schema: `/openapi.json`.

**Tunnel for phones / ngrok** (install [ngrok](https://ngrok.com/) separately; it is not part of this repo):

```bash
ngrok http 8000
```

Use the HTTPS forwarding URL the tool prints as the base URL in the app during development.


## API overview

All routes below require header `**X-API-Key**` (value must match the server’s `BLUEMESH_API_KEY`). JSON bodies use `Content-Type: application/json` where applicable.


| Method | Path                          | Role                                                                               |
| ------ | ----------------------------- | ---------------------------------------------------------------------------------- |
| `POST` | `/message`                    | Submit a message for a recipient (`to`).                                           |
| `GET`  | `/messages/{app_id}`          | Recipient polls inbox; messages are **returned then deleted** (one-time delivery). |
| `GET`  | `/relay-pending`              | Bridge lists messages still in the DB for relay; **read-only** (not deleted).      |
| `POST` | `/relay-confirm/{message_id}` | After BLE delivery, bridge tells server to **delete** that message by id.          |


### `POST /message`

- **Body:** `{ "messageId": "<string>", "from": "<8 hex chars>", "to": "<8 hex chars>", "content": "<string>" }`  
`from` / `to` are device IDs (lowercase hex, 8 characters). `messageId` is the deduplication key (typically a UUID string).
- **200:** `{"ok": true}` — accepted, or duplicate `messageId` (second insert ignored, still 200).
- **422:** validation error (e.g. bad hex length).

### `GET /messages/{app_id}`

- **Path:** `app_id` — 8 hex characters (case-insensitive).
- **200:** JSON array of `{ "messageId", "from", "content", "receivedAt" }` where `receivedAt` is ISO-8601 UTC with a `Z` suffix. Empty inbox: `[]`.
- After a successful response, those rows are **removed** from the database.

### `GET /relay-pending`

- **200:** JSON array of `{ "messageId", "from", "to", "content" }` for messages still pending relay (`delivered = 0` in DB). Empty: `[]`. Rows stay in the DB until direct poll or relay confirm removes them.

### `POST /relay-confirm/{message_id}`

- **Path:** `message_id` — same opaque string as `messageId` when the message was posted (no 8-char hex restriction on this segment).
- **Body:** none.
- **200:** `{"ok": true}` — row deleted if it existed; idempotent if already gone.


## Data model (SQLite)

Single table `**messages`**: `id`, `message_id` (unique), `from_app_id`, `to_app_id`, `content`, `received_at` (Unix ms), `delivered` (integer flag, default 0). Index on `to_app_id`.


## Logging

Each server process writes request/response lines under `logs/` in a new timestamped `.log` file (directory is gitignored).