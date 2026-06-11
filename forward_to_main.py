#!/usr/bin/env python3
"""Forward incoming DMs and mentions from Алексей account to @leshchenko1979.

Runs via cron every ~2 minutes. Polls messages.GetDialogs + messages.GetHistory
via the fast-mcp-telegram bridge and forwards new relevant messages.
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BRIDGE_URL = os.getenv("BRIDGE_URL", "http://localhost:8000")
BEARER_TOKEN = os.getenv("BEARER_TOKEN", "")
TARGET = os.getenv("TARGET_USER", "leshchenko1979")
STATE_FILE = os.getenv("STATE_FILE", "/data/projects/forwarder/state.json")
FIRST_BACK = int(os.getenv("FIRST_BACK_MINUTES", "60"))
MAX_FWD = 30  # max messages to forward per run
TELEGRAM_USER_ID = 777000  # Telegram notification service user
BLACKLIST_NAMES = ["редевест - дела", "редевест-дела"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("fwd")


# ── bridge API ──────────────────────────────────────────────────────────


def api(method: str, params: dict | None = None) -> dict:
    data = json.dumps({"params": params or {}}).encode()
    req = Request(
        f"{BRIDGE_URL}/mtproto-api/{method}",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {BEARER_TOKEN}",
        },
    )
    try:
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except HTTPError as e:
        try:
            err = json.loads(e.read().decode())
            raise RuntimeError(err.get("error", str(e)))
        except (ValueError, json.JSONDecodeError):
            raise RuntimeError(str(e))
    except URLError as e:
        raise RuntimeError(f"bridge unreachable: {e}")


# ── state persistence ──────────────────────────────────────────────────


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {"ts": 0, "forwarded_ids": {}}


def save_state(ts: int, forwarded_ids: dict[str, int] | None = None) -> None:
    Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    state = {"ts": ts}
    if forwarded_ids:
        state["forwarded_ids"] = forwarded_ids
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── peer helpers ───────────────────────────────────────────────────────
# We pass raw peer IDs to the bridge — it resolves them via Telethon's
# get_input_entity() using the cached entities in the session file.


def peer_id(peer_dict: dict) -> int | None:
    return (
        peer_dict.get("user_id")
        or peer_dict.get("channel_id")
        or peer_dict.get("chat_id")
    )


def msg_peer_key(msg: dict) -> str:
    """Unique key for the dialog this message belongs to."""
    pid = peer_id(msg.get("peer_id", {}))
    return str(pid) if pid else "0"


# ── relevance filters & entity display ────────────────────────────────


def is_relevant(msg: dict) -> bool:
    """True if message should be forwarded: DMs (all) + group/channel mentions."""
    if msg.get("_") in ("messageEmpty", "messageService", None):
        return False
    # Skip "From @user:" headers created by the forwarder itself
    msg_text = msg.get("message", "") or ""
    if "[fwd-" in msg_text:
        return False
    ptype = msg.get("peer_id", {}).get("_", "")
    # All private chats
    if ptype in ("peerUser", "PeerUser"):
        uid = msg.get("peer_id", {}).get("user_id")
        if uid == TELEGRAM_USER_ID:
            return False  # Telegram notifications (security codes, login)
        return True
    # Group/channel — only if Алексей was mentioned (NOT post/channel broadcast)
    if ptype in ("peerChat", "PeerChat", "peerChannel", "PeerChannel"):
        return msg.get("mentioned", False)
    return False


def build_entity_maps(dialogs_data: dict) -> tuple[dict, dict]:
    """Build user_id→user and chat_id→chat lookup from GetDialogs response."""
    users = {}
    for u in dialogs_data.get("users", []):
        if u.get("id"):
            users[u["id"]] = u
    chats = {}
    for c in dialogs_data.get("chats", []):
        if c.get("id"):
            chats[c["id"]] = c
    return users, chats


def get_entity_display(
    peer: dict, users: dict[int, dict], chats: dict[int, dict]
) -> str:
    """Get a human-readable display name for a dialog peer."""
    if not isinstance(peer, dict):
        return str(peer)

    peer_type = peer.get("_")
    if peer_type in ("peerUser", "PeerUser"):
        uid = peer.get("user_id")
        if uid and uid in users:
            u = users[uid]
            username = u.get("username")
            if username:
                return f"@{username}"
            name = f"{u.get('first_name', '')} {u.get('last_name', '')}".strip()
            return name or str(uid)
        return str(uid) if uid else "?"
    elif peer_type in ("peerChat", "PeerChat"):
        cid = peer.get("chat_id")
        if cid and cid in chats:
            c = chats[cid]
            return c.get("title", "") or str(cid)
        return str(cid) if cid else "?"
    elif peer_type in ("peerChannel", "PeerChannel"):
        cid = peer.get("channel_id")
        if cid and cid in chats:
            c = chats[cid]
            username = c.get("username")
            return f"@{username}" if username else c.get("title", "") or str(cid)
        return str(cid) if cid else "?"
    return str(peer)


# ── main poll loop ─────────────────────────────────────────────────────


def main() -> int:
    state = load_state()
    now_ts = int(time.time())
    last_ts = state.get("ts", 0) or now_ts - FIRST_BACK * 60
    forwarded_ids: dict[str, int] = state.get("forwarded_ids", {})

    log.info(
        "Polling since %s",
        datetime.fromtimestamp(last_ts, tz=timezone.utc).isoformat(),
    )

    # 1. Get all recent dialogs
    try:
        d = api("messages.GetDialogs", {
            "offset_date": 0,
            "offset_id": 0,
            "offset_peer": {"_": "inputPeerEmpty"},
            "limit": 100,
            "hash": 0,
        })
    except RuntimeError as e:
        log.error("GetDialogs failed: %s", e)
        return 0

    # Build entity lookup maps for dialog header display names
    users_map, chats_map = build_entity_maps(d)
    dialogs = d.get("dialogs", [])
    log.info("Dialogs: %d", len(dialogs))

    total_fwd = 0
    max_ts = last_ts  # track the newest date seen

    for dialog in dialogs:
        p = dialog.get("peer", {})
        dialog_pid = peer_id(p)
        if not dialog_pid:
            continue

        # 2. Get recent history for this dialog
        try:
            hist = api("messages.GetHistory", {
                "peer": dialog_pid,
                "offset_id": 0,
                "offset_date": 0,
                "add_offset": 0,
                "limit": 50,
                "max_id": 0,
                "min_id": 0,
                "hash": 0,
            })
        except RuntimeError as e:
            log.debug("GetHistory fail peer=%s: %s", dialog_pid, e)
            continue

        msgs = hist.get("messages", [])
        # Track whether we've sent the "From" header for this dialog
        header_sent = False
        header_key = None  # to avoid duplicate headers if multiple relevant msgs
        header_msg_id = None
        fwd_success = False

        for msg in reversed(msgs):  # oldest first
            raw_date = msg.get("date") or 0
            if isinstance(raw_date, (int, float)):
                mdate = int(raw_date)
            elif isinstance(raw_date, str):
                try:
                    dt = datetime.fromisoformat(raw_date)
                    mdate = int(dt.timestamp())
                except ValueError:
                    mdate = 0
            else:
                mdate = 0
            if mdate > max_ts:
                max_ts = mdate

            if mdate <= last_ts:
                continue  # already scanned

            if not is_relevant(msg):
                continue

            # 3. Check dedup by dialog + message_id
            key = f"{dialog_pid}:{msg.get('id')}"
            if forwarded_ids.get(key) == msg.get("id"):
                continue

            # 4. Send "From @..." header once per dialog
            if not header_sent:
                display = get_entity_display(p, users_map, chats_map)
                # Skip blacklisted dialogs
                if any(excl.lower() in display.lower() for excl in BLACKLIST_NAMES):
                    log.info("Skipping blacklisted: %s", display)
                    break
                try:
                    result = api("messages.SendMessage", {
                        "peer": f"@{TARGET}",
                        "message": f"From {display}: [fwd-{random.randint(0, 2_147_483_647):x}]",
                    })
                    time.sleep(0.3)
                    header_sent = True
                    header_key = display
                    header_msg_id = result.get("id") if isinstance(result, dict) else None
                    log.info("Header: From %s", display)
                except RuntimeError as e:
                    log.warning("Header send failed for %s: %s", display, e)

            # 5. Forward the message
            mid = msg.get("id")
            from_pid = peer_id(msg.get("peer_id", {}))
            if not from_pid or not mid:
                continue

            try:
                api("messages.ForwardMessages", {
                    "from_peer": from_pid,
                    "id": [mid],
                    "to_peer": f"@{TARGET}",
                    "random_id": [random.randint(0, 2_147_483_647)],
                })
                preview = (msg.get("message") or "")[:80]
                log.info(">> %s | msg=%s", preview, mid)
                forwarded_ids[key] = mid
                fwd_success = True
                total_fwd += 1
                if total_fwd >= MAX_FWD:
                    log.info("Reached cap of %d, stopping", MAX_FWD)
                    break
            except RuntimeError as e:
                log.warning("! fwd fail msg=%s peer=%s: %s", mid, from_pid, e)

        # Cleanup orphan header if nothing was forwarded
        if header_sent and not fwd_success and header_msg_id:
            try:
                api("messages.DeleteMessages", {"id": [header_msg_id]})
                log.info("Deleted orphan header for %s", header_key or "?")
            except RuntimeError as e:
                log.warning("Could not delete orphan header: %s", e)

        if total_fwd >= MAX_FWD:
            log.info("Cap reached, stopping dialog scan")
            break

    # 6. Save state
    save_state(max(max_ts, now_ts), forwarded_ids)
    log.info("Forwarded %d messages", total_fwd)
    return total_fwd


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log.critical("Fatal: %s", e, exc_info=True)
        raise
