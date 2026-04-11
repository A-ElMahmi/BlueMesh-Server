# Server Brief: Hybrid BLE-Internet Messaging Gateway

## Overview

This is a proof-of-concept messaging app that bridges Bluetooth Low Energy (BLE) mesh communication with internet-based delivery. The server acts as a simple **message inbox** — it stores messages for devices that cannot be reached directly and delivers them when those devices check in.

The server has no concept of users, accounts, or sessions. Every device is identified solely by its **`appId`**: a stable 8-character hex string (e.g. `a3f9bc12`) generated once per app installation and persisted on the device.

---

## Device Types in the System

| Device | Internet | Bluetooth | Role |
|--------|----------|-----------|------|
| **A** | No | Yes | Sender — BLE only |
| **B** | Yes | Yes | Bridge — receives from A over BLE, forwards to server |
| **C** | Yes | No (for now) | Recipient — polls server for messages |

This is the only scenario being built for now. Reverse direction (C → A) is out of scope.

---

## Message Flow

### Scenario 1: A has internet (simple case)
A sends the message **directly to the server**. No BLE involved.

```
A ──────── POST /message ──────────► Server ──► C polls ──► C receives
```

### Scenario 2: A has no internet
A scans for C over BLE for 3 seconds. If C is not found directly:

1. A floods the message to **all visible BLE neighbors** (one at a time, sequentially)
2. Each neighbor that receives the message independently decides:
   - **Has internet** → forwards to server
   - **No internet** → drops the message (no further forwarding)
3. C polls the server and retrieves the message

```
A ──BLE──► B1 ──── POST /message ───► Server ──► C polls ──► C receives
A ──BLE──► B2 ──── POST /message ───► Server   (duplicate, ignored by server)
A ──BLE──► B3 (no internet) ──► DROP
```

---

## Server Responsibilities

The server does three things only:

1. **Accept** incoming messages and store them in the recipient's inbox
2. **Deduplicate** — if the same message arrives twice (same `messageId`), ignore the second one
3. **Serve** queued messages to a polling device and clear them after delivery
4. **Expire** messages older than 24 hours (they will never be delivered)

The server does **not** maintain connections, sessions, or any concept of online/offline status. It is purely a store-and-forward relay.

---

## API

### `POST /message`
A device (either A directly, or B as a bridge) submits a message for delivery.

**Request body (JSON):**
```json
{
  "messageId": "550e8400-e29b-41d4-a716-446655440000",
  "from":      "a3f9bc12",
  "to":        "d7e2aa09",
  "content":   "Hello from A"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `messageId` | UUID string | Unique ID for this message. Used for deduplication. |
| `from` | 8-char hex string | Sender's `appId` |
| `to` | 8-char hex string | Recipient's `appId` |
| `content` | string | The message text |

**Response:**
- `200 OK` — message accepted (or silently ignored as duplicate)
- `400 Bad Request` — missing or malformed fields

**Deduplication rule:** If a message with the same `messageId` already exists in the database, discard the new one and still return `200`. Do not return an error.

---

### `GET /messages/:appId`
A device polls for its pending messages.

**URL parameter:** `appId` — the polling device's own `appId`

**Response (JSON):**
```json
[
  {
    "messageId": "550e8400-e29b-41d4-a716-446655440000",
    "from":      "a3f9bc12",
    "content":   "Hello from A",
    "receivedAt": "2026-04-01T14:32:00Z"
  }
]
```

Returns an empty array `[]` if no messages are pending.

**Important:** After returning messages, **delete them from the database**. This is a one-time delivery model — messages are not re-delivered on subsequent polls. If the app crashes after receiving but before displaying, those messages are lost. This is acceptable for PoC.

**Polling interval from the app:** every **15 seconds** while the app is open.

---

## Database Schema

A single table is sufficient:

```sql
CREATE TABLE messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id  TEXT    NOT NULL UNIQUE,   -- for deduplication
  from_app_id TEXT    NOT NULL,
  to_app_id   TEXT    NOT NULL,
  content     TEXT    NOT NULL,
  received_at INTEGER NOT NULL           -- Unix timestamp (ms)
);

CREATE INDEX idx_to_app_id ON messages(to_app_id);
```

The `UNIQUE` constraint on `message_id` enforces deduplication at the database level — no application logic needed beyond catching the constraint violation and returning `200`.

For expiry, run a cleanup on every `POST /message` call (or on a timer):
```sql
DELETE FROM messages WHERE received_at < (now - 86400000);
```

---

## Important Considerations

### Security
There is **no authentication**. Any client that knows an `appId` can:
- Submit messages pretending to be any sender (`from` is not verified)
- Retrieve messages for any `appId` by hitting `GET /messages/:appId`

This is intentional for PoC. Do not put real users on this. Before production, you would need at minimum a shared secret or signed requests.

### Deduplication
Multiple bridge devices (B1, B2...) may forward the same message to the server independently. The `messageId` field combined with the `UNIQUE` constraint handles this. The app generates a UUID per message before sending — the server just enforces uniqueness.

### Message Expiry
Expire messages after **24 hours**. No delivery after that.

### Server URL
The app will use a **ngrok endpoint** pointing at your localhost during development. The URL is hardcoded in the app as a constant. You don't need to handle any dynamic discovery — just give the team the ngrok URL.

### Scale
This is a PoC. No load considerations. A single Node.js process with SQLite is the expected stack.