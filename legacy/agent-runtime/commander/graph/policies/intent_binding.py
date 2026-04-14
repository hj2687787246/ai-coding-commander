from __future__ import annotations

import re
from typing import Any


_PUNCTUATION = " \t\r\n,.;:!?~`'\"()[]{}<>|/\\，。；：！？～`'\"（）【】《》、"
_SHORT_CONFIRMATIONS = {
    "ok",
    "okay",
    "yes",
    "yep",
    "可以",
    "可以的",
    "可",
    "继续",
    "继续吧",
    "继续做",
    "行",
    "行吧",
    "好",
    "好的",
    "好呀",
    "好哦",
    "嗯",
    "嗯嗯",
    "收到",
}


def _normalize_optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().strip(_PUNCTUATION).strip()
    return normalized or None


def _normalize_confirmation_key(value: Any) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    compact = re.sub(r"\s+", "", normalized).lower()
    return compact or None


def _normalize_offer(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None

    summary = _normalize_optional_text(payload.get("summary"))
    proposed_action = _normalize_optional_text(payload.get("proposed_action"))
    offer_id = _normalize_optional_text(
        payload.get("offer_id")
        or payload.get("proposal_id")
        or payload.get("target_id")
        or payload.get("id")
    )
    if offer_id is None:
        offer_id = proposed_action or summary
    if offer_id is None:
        return None

    return {
        "offer_id": offer_id,
        "summary": summary,
        "proposed_action": proposed_action,
        "created_at": _normalize_optional_text(payload.get("created_at")),
        "source_message_id": _normalize_optional_text(payload.get("source_message_id")),
    }


def is_short_confirmation(text: Any) -> bool:
    normalized = _normalize_confirmation_key(text)
    return normalized in _SHORT_CONFIRMATIONS if normalized is not None else False


def build_intent_binding_state(
    *,
    existing: Any = None,
    update: dict[str, Any] | None = None,
) -> dict[str, Any]:
    existing_payload = existing if isinstance(existing, dict) else {}
    update_payload = update if isinstance(update, dict) else {}

    previous_offer = _normalize_offer(existing_payload.get("last_open_offer"))
    if "last_open_offer" in update_payload:
        current_offer = _normalize_offer(update_payload.get("last_open_offer"))
    else:
        current_offer = previous_offer

    offer_changed = (
        (previous_offer or {}).get("offer_id") != (current_offer or {}).get("offer_id")
    )

    if "pending_user_reply_target" in update_payload:
        pending_user_reply_target = _normalize_optional_text(
            update_payload.get("pending_user_reply_target")
        )
    else:
        pending_user_reply_target = _normalize_optional_text(
            existing_payload.get("pending_user_reply_target")
        )
    if pending_user_reply_target is None and current_offer is not None:
        pending_user_reply_target = current_offer.get("offer_id")

    latest_user_reply_text: str | None
    if "latest_user_reply_text" in update_payload:
        latest_user_reply_text = _normalize_optional_text(
            update_payload.get("latest_user_reply_text")
        )
    elif offer_changed:
        latest_user_reply_text = None
    else:
        latest_user_reply_text = _normalize_optional_text(
            existing_payload.get("latest_user_reply_text")
        )

    if latest_user_reply_text is None:
        latest_user_reply_kind = "none"
    elif is_short_confirmation(latest_user_reply_text):
        latest_user_reply_kind = "short_confirmation"
    else:
        latest_user_reply_kind = "freeform_reply"

    explicit_offer_confirmed = update_payload.get("offer_confirmed")
    if isinstance(explicit_offer_confirmed, bool):
        offer_confirmed = explicit_offer_confirmed
        binding_reason = "explicit_offer_confirmation_override"
    elif latest_user_reply_kind == "short_confirmation":
        offer_confirmed = pending_user_reply_target is not None
        if offer_confirmed:
            binding_reason = "short_confirmation_bound_to_latest_open_offer"
        else:
            binding_reason = "short_confirmation_without_open_offer"
    elif offer_changed:
        offer_confirmed = False
        binding_reason = (
            "awaiting_user_reply_for_latest_offer"
            if pending_user_reply_target is not None
            else "no_open_offer"
        )
    else:
        offer_confirmed = bool(existing_payload.get("offer_confirmed"))
        if latest_user_reply_kind == "freeform_reply":
            offer_confirmed = False
            binding_reason = "freeform_reply_requires_normal_intent_resolution"
        elif offer_confirmed:
            binding_reason = "offer_already_confirmed"
        elif pending_user_reply_target is not None:
            binding_reason = "awaiting_user_reply_for_latest_offer"
        else:
            binding_reason = "no_open_offer"

    resolved_reply_target = pending_user_reply_target if offer_confirmed else None

    return {
        "last_open_offer": current_offer,
        "pending_user_reply_target": pending_user_reply_target,
        "offer_confirmed": offer_confirmed,
        "latest_user_reply_text": latest_user_reply_text,
        "latest_user_reply_kind": latest_user_reply_kind,
        "resolved_reply_target": resolved_reply_target,
        "binding_reason": binding_reason,
    }
