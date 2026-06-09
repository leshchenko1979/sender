"""HTTP bridge to fast-mcp-telegram MTProto API.

Replaces Telethon/tg library with direct HTTP calls to fast-mcp-telegram
running on the traefik-public Docker network.

Uses only stdlib urllib — no external HTTP dependencies.
Each client provides its own Bearer token for the bridge.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

BRIDGE_TIMEOUT = 15
MTROTO_BASE = os.environ.get(
    "FAST_MCP_BASE", "http://fast-mcp-telegram:8000/mtproto-api"
)
"""Default base URL for the fast-mcp-telegram MTProto bridge."""


class MtProtoError(Exception):
    """Raised when the bridge returns an error response."""

    def __init__(self, method: str, detail: str):
        self.method = method
        self.detail = detail
        super().__init__(f"{method}: {detail}")


def _call(
    method: str, params: dict | None = None, bearer_token: str | None = None
) -> dict:
    """POST to the MTProto bridge and return the JSON result.

    Args:
        method: Full TL method name, e.g. "messages.ForwardMessages".
        params: Parameters for the method (will be JSON-encoded).
        bearer_token: Bearer token for fast-mcp-telegram auth.
                      Falls back to FAST_MCP_BEARER env var.

    Returns:
        Decoded "result" dict from the bridge response.

    Raises:
        MtProtoError: If the bridge returns an error or connection fails.
    """
    url = f"{MTROTO_BASE.rstrip('/')}/{method.removeprefix('/')}"
    body = json.dumps({"params": params or {}}).encode("utf-8")

    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token := bearer_token or os.environ.get("FAST_MCP_BEARER", ""):
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=BRIDGE_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise MtProtoError(method, f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise MtProtoError(method, f"Connection failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise MtProtoError(method, f"Invalid JSON response: {exc}") from exc

    if not payload.get("ok"):
        err = payload.get("error", payload.get("detail", None))
        if err is None:
            err_code = payload.get("code", "")
            err_msg = payload.get("exception", {}).get("message", "")
            if err_code or err_msg:
                parts = [f"code={err_code}"] if err_code else []
                if err_msg:
                    parts.append(f"message={err_msg}")
                err = " ".join(parts)
            else:
                safe_payload = {
                    k: v
                    for k, v in payload.items()
                    if k in ("error", "code", "exception")
                }
                err = f"unknown error (payload: {json.dumps(safe_payload, ensure_ascii=False)[:300]})"
        raise MtProtoError(method, str(err))

    return payload.get("result", {})


# ── High-level helpers ────────────────────────────────────────────────


def forward_messages(
    from_peer: str,
    to_peer: str,
    message_ids: list[int],
    top_msg_id: int | None = None,
    drop_author: bool = True,
    bearer_token: str | None = None,
) -> dict:
    """Forward messages between chats via the MTProto bridge.

    Args:
        bearer_token: Per-client bridge token (overrides env default).

    Returns:
        Raw TL result from messages.ForwardMessages.
    """
    params = {
        "from_peer": from_peer,
        "to_peer": to_peer,
        "id": message_ids,
        "drop_author": drop_author,
    }
    if top_msg_id is not None:
        params["top_msg_id"] = top_msg_id
    return _call("messages.ForwardMessages", params, bearer_token=bearer_token)


def send_message(
    peer: str,
    text: str,
    reply_to: int | None = None,
    bearer_token: str | None = None,
) -> dict:
    """Send a plain text message via the MTProto bridge.

    Args:
        bearer_token: Per-client bridge token (overrides env default).

    Returns:
        Raw TL result from messages.SendMessage.
    """
    params = {"peer": peer, "message": text}
    if reply_to is not None:
        params["reply_to"] = reply_to
    return _call("messages.SendMessage", params, bearer_token=bearer_token)


def get_history(
    peer: str,
    limit: int = 20,
    offset_id: int = 0,
    add_offset: int = 0,
    max_id: int = 0,
    min_id: int = 0,
    bearer_token: str | None = None,
) -> dict:
    """Retrieve message history from a chat.

    Args:
        bearer_token: Per-client bridge token (overrides env default).

    Returns:
        Raw TL result from messages.GetHistory.
    """
    params = {
        "peer": peer,
        "limit": limit,
        "max_id": max_id,
        "min_id": min_id,
    }
    if offset_id > 0:
        params["offset_id"] = offset_id
    if add_offset != 0:
        params["add_offset"] = add_offset
    return _call("messages.GetHistory", params, bearer_token=bearer_token)


def get_messages(
    peer: str,
    ids: list[int],
    bearer_token: str | None = None,
) -> dict:
    """Retrieve specific messages by ID.

    NOTE: `peer` is accepted for backward compatibility but NOT sent to the
    bridge — messages.GetMessagesRequest only accepts `id`, not `peer`.
    The Telegram API resolves message IDs across accessible dialogs.

    Args:
        bearer_token: Per-client bridge token (overrides env default).

    Returns:
        Raw TL result from messages.GetMessages.
    """
    return _call("messages.GetMessages", {"id": ids}, bearer_token=bearer_token)


def join_channel(channel: str, bearer_token: str | None = None) -> dict:
    """Join a public channel or supergroup.

    Args:
        bearer_token: Per-client bridge token (overrides env default).

    Returns:
        Raw TL result from channels.JoinChannel.
    """
    return _call(
        "channels.JoinChannel", {"channel": channel}, bearer_token=bearer_token
    )


def import_chat_invite(hash_or_link: str, bearer_token: str | None = None) -> dict:
    """Join a private chat via invite link.

    Args:
        bearer_token: Per-client bridge token (overrides env default).

    Returns:
        Raw TL result from messages.ImportChatInvite.
    """
    return _call(
        "messages.ImportChatInvite", {"hash": hash_or_link}, bearer_token=bearer_token
    )


def delete_messages(peer: str, ids: list[int], bearer_token: str | None = None) -> dict:
    """Delete messages from a chat.

    NOTE: `peer` is accepted for backward compatibility but NOT sent to the
    bridge — messages.DeleteMessagesRequest only accepts `id`, not `peer`.
    Message IDs are resolved by the Telegram API across accessible dialogs.

    Args:
        bearer_token: Per-client bridge token (overrides env default).

    Returns:
        Raw TL result from messages.DeleteMessages.
    """
    return _call("messages.DeleteMessages", {"id": ids}, bearer_token=bearer_token)
