"""
Tools Gmail + Google Calendar pour Orion.

S'appuie sur server/google_auth.py pour le flow OAuth.
Tous les handlers retournent {"success": bool, ...} comme les autres tools Orion.

Inspiré des connecteurs OpenJarvis (Stanford SAIL, Apache 2.0), simplifié pour
utiliser google-api-python-client directement au lieu d'httpx + OAuth maison.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any

from server.google_auth import calendar_service, gmail_service, google_setup_status


# ════════════════════════════════════════════════════════════════════════════
# GMAIL
# ════════════════════════════════════════════════════════════════════════════

def _gmail_extract_header(headers: list[dict], name: str) -> str:
    name_l = name.lower()
    for h in headers:
        if h.get("name", "").lower() == name_l:
            return h.get("value", "")
    return ""


def _gmail_extract_text(payload: dict) -> str:
    """Extrait le corps texte (plain text) d'un message Gmail."""
    if not payload:
        return ""
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})

    if mime_type.startswith("text/plain") and body.get("data"):
        try:
            return base64.urlsafe_b64decode(body["data"]).decode("utf-8", errors="replace")
        except Exception:
            return ""

    for part in payload.get("parts", []):
        text = _gmail_extract_text(part)
        if text:
            return text
    return ""


def gmail_search(input: dict) -> dict:
    """Cherche des emails. Input: {query, max_results}.

    Format query : syntaxe Gmail standard
    (ex: 'is:unread', 'from:boss@example.com', 'subject:facture')
    """
    query = (input.get("query") or "").strip()
    max_results = int(input.get("max_results") or 10)
    max_results = max(1, min(max_results, 50))

    try:
        service = gmail_service()
        resp = service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        messages = resp.get("messages", [])

        results = []
        for ref in messages:
            full = service.users().messages().get(
                userId="me", id=ref["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = full.get("payload", {}).get("headers", [])
            from_raw = _gmail_extract_header(headers, "From")
            from_name, from_email = parseaddr(from_raw)
            results.append({
                "id": full["id"],
                "thread_id": full.get("threadId"),
                "from": from_email or from_raw,
                "from_name": from_name or from_email or from_raw,
                "subject": _gmail_extract_header(headers, "Subject"),
                "date": _gmail_extract_header(headers, "Date"),
                "snippet": full.get("snippet", ""),
                "unread": "UNREAD" in full.get("labelIds", []),
            })
        return {"success": True, "count": len(results), "messages": results}
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc), "setup": google_setup_status()}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def gmail_read_message(input: dict) -> dict:
    """Lit le contenu complet d'un email. Input: {message_id, max_chars}."""
    msg_id = (input.get("message_id") or "").strip()
    if not msg_id:
        return {"success": False, "error": "message_id requis"}
    max_chars = int(input.get("max_chars") or 8000)

    try:
        service = gmail_service()
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])
        body = _gmail_extract_text(payload)
        if len(body) > max_chars:
            body = body[:max_chars] + "\n[…tronqué]"
        return {
            "success": True,
            "id": msg["id"],
            "from": _gmail_extract_header(headers, "From"),
            "to": _gmail_extract_header(headers, "To"),
            "cc": _gmail_extract_header(headers, "Cc"),
            "subject": _gmail_extract_header(headers, "Subject"),
            "date": _gmail_extract_header(headers, "Date"),
            "body": body,
            "labels": msg.get("labelIds", []),
        }
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc), "setup": google_setup_status()}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


# ════════════════════════════════════════════════════════════════════════════
# GOOGLE CALENDAR
# ════════════════════════════════════════════════════════════════════════════

def _isoformat_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_event(event: dict) -> dict:
    start = event.get("start") or {}
    end = event.get("end") or {}
    return {
        "id": event.get("id"),
        "summary": event.get("summary", "(sans titre)"),
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
        "all_day": "date" in start and "dateTime" not in start,
        "html_link": event.get("htmlLink", ""),
        "attendees": [
            {"email": a.get("email"), "response": a.get("responseStatus")}
            for a in event.get("attendees", [])
        ],
    }


def calendar_list_events(input: dict) -> dict:
    """Liste les événements à venir. Input: {max_results, days_ahead, calendar_id}."""
    max_results = int(input.get("max_results") or 10)
    max_results = max(1, min(max_results, 50))
    days_ahead = int(input.get("days_ahead") or 7)
    calendar_id = (input.get("calendar_id") or "primary").strip() or "primary"

    now = datetime.now(timezone.utc)
    time_min = _isoformat_z(now)
    time_max = _isoformat_z(now + timedelta(days=days_ahead))

    try:
        service = calendar_service()
        resp = service.events().list(
            calendarId=calendar_id,
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = [_normalize_event(e) for e in resp.get("items", [])]
        return {
            "success": True,
            "calendar_id": calendar_id,
            "from": time_min,
            "to": time_max,
            "count": len(events),
            "events": events,
        }
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc), "setup": google_setup_status()}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


def calendar_create_event(input: dict) -> dict:
    """Crée un événement. Input: {summary, start, end, description?, location?, attendees?}.

    Formats start/end : ISO 8601 (ex: '2026-05-15T14:00:00+02:00') ou
    'YYYY-MM-DD' pour un événement journée entière.
    """
    summary = (input.get("summary") or "").strip()
    start = (input.get("start") or "").strip()
    end = (input.get("end") or "").strip()
    if not summary or not start or not end:
        return {"success": False, "error": "summary, start et end sont requis"}

    description = input.get("description") or ""
    location = input.get("location") or ""
    attendees = input.get("attendees") or []
    calendar_id = (input.get("calendar_id") or "primary").strip() or "primary"

    def _time_field(value: str) -> dict:
        # Si pas d'heure, on suppose une journée entière
        if "T" not in value:
            return {"date": value}
        return {"dateTime": value}

    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": _time_field(start),
        "end": _time_field(end),
    }
    if attendees:
        body["attendees"] = [{"email": a} for a in attendees if isinstance(a, str)]

    try:
        service = calendar_service()
        created = service.events().insert(
            calendarId=calendar_id, body=body, sendUpdates="none"
        ).execute()
        return {
            "success": True,
            "event": _normalize_event(created),
            "html_link": created.get("htmlLink"),
        }
    except FileNotFoundError as exc:
        return {"success": False, "error": str(exc), "setup": google_setup_status()}
    except Exception as exc:
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}


HANDLERS = {
    "gmail_search": gmail_search,
    "gmail_read_message": gmail_read_message,
    "calendar_list_events": calendar_list_events,
    "calendar_create_event": calendar_create_event,
}
