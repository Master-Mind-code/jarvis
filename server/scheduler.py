"""
Scheduler interne d'Orion : tâches récurrentes auto (briefing matinal, …).

Tourne dans un thread daemon attaché au serveur. Précision : ~30 s.

Format des jobs (server.scheduler.JOBS) :
    {
        "id": "morning_briefing",
        "schedule": {"hour": 8, "minute": 0, "weekdays": [0,1,2,3,4]},
        "enabled": True,
        "fn": <callable>,
    }

Active/désactive via .env :
    ORION_BRIEFING_ENABLED=true
    ORION_BRIEFING_TIME=08:00
    ORION_BRIEFING_WEEKDAYS=mon,tue,wed,thu,fri
    ORION_BRIEFING_DEVICE=voice-astrakernel  (broadcast vers ce device pour TTS)
"""
from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timedelta

from branding import get_env

WEEKDAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
               "lun": 0, "mar": 1, "mer": 2, "jeu": 3, "ven": 4, "sam": 5, "dim": 6}


def _parse_time(s: str, default=(8, 0)) -> tuple[int, int]:
    try:
        h, m = s.split(":")
        return int(h), int(m)
    except Exception:
        return default


def _parse_weekdays(s: str | None) -> set[int]:
    if not s:
        return {0, 1, 2, 3, 4}  # lundi-vendredi
    out = set()
    for tok in s.split(","):
        t = tok.strip().lower()[:3]
        if t in WEEKDAY_MAP:
            out.add(WEEKDAY_MAP[t])
    return out or {0, 1, 2, 3, 4}


def _env_bool(name: str, default: bool) -> bool:
    raw = get_env(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on", "oui")


class Scheduler:
    def __init__(self):
        self.jobs: list[dict] = []
        self._stop_event = threading.Event()
        self._last_run: dict[str, str] = {}  # id → "YYYY-MM-DD-HH-MM"

    def register_job(self, job: dict):
        if any(j["id"] == job["id"] for j in self.jobs):
            return
        self.jobs.append(job)
        print(f"[scheduler] + {job['id']} ({job['schedule']})")

    def _should_run(self, job: dict, now: datetime) -> bool:
        sched = job["schedule"]
        if not job.get("enabled", True):
            return False
        if now.weekday() not in sched.get("weekdays", set()):
            return False
        if now.hour != sched.get("hour"):
            return False
        if now.minute != sched.get("minute"):
            return False
        # Anti-double-déclenchement (1 fois par minute max)
        slot = now.strftime("%Y-%m-%d-%H-%M")
        if self._last_run.get(job["id"]) == slot:
            return False
        self._last_run[job["id"]] = slot
        return True

    def _run_job(self, job: dict):
        print(f"[scheduler] ▶ {job['id']}")
        try:
            result = job["fn"]()
            if asyncio.iscoroutine(result):
                # Job async : on le lance dans une boucle dédiée (thread isolé)
                asyncio.run(result)
        except Exception as exc:
            print(f"[scheduler!] {job['id']} a échoué : {exc}")

    def _loop(self):
        while not self._stop_event.is_set():
            now = datetime.now()
            for job in self.jobs:
                if self._should_run(job, now):
                    threading.Thread(target=self._run_job, args=(job,), daemon=True).start()
            # Reveille à la minute suivante (approx)
            time.sleep(30)

    def start(self):
        if not self.jobs:
            print("[scheduler] Aucun job enregistré, scheduler en sommeil.")
            return
        thread = threading.Thread(target=self._loop, daemon=True, name="orion-scheduler")
        thread.start()
        print(f"[scheduler] {len(self.jobs)} job(s) actif(s).")

    def stop(self):
        self._stop_event.set()


# Singleton global
SCHEDULER = Scheduler()


# ════════════════════════════════════════════════════════════════════════════
# Job : briefing matinal vocal
# ════════════════════════════════════════════════════════════════════════════
def _briefing_prompt() -> str:
    """Construit la requête envoyée à Orion pour générer le briefing."""
    return (
        "Génère un briefing matinal court et naturel à voix haute pour ton "
        "utilisateur. Tu DOIS utiliser les tools dans cet ordre si dispo :\n"
        "1. fetch_url ou web_search pour la météo locale\n"
        "2. calendar_list_events pour l'agenda du jour (days_ahead=1)\n"
        "3. gmail_search query='is:unread newer_than:1d' pour les emails non lus\n"
        "Puis synthétise en 4-6 phrases courtes : météo, agenda, emails clés. "
        "Pas de markdown, pas d'emoji (sera lu par TTS). Commence par 'Bonjour !'"
    )


def _run_morning_briefing():
    """Lance un briefing matinal en injectant un message dans la session du device cible."""
    # Import retardé pour éviter les cycles
    from server import main as srv_main
    from server.orchestrator import process_request_streaming

    device = (get_env("BRIEFING_DEVICE") or "").strip()
    if not device:
        # Cherche un controller "voice-*" actif comme target par défaut
        for did in srv_main.controllers.keys():
            if did.startswith("voice-"):
                device = did
                break
    if not device:
        print("[briefing!] Aucun device 'voice-*' connecté. Skip.")
        return

    session = srv_main.controllers.get(device)
    if not session or not session.get("ws"):
        print(f"[briefing!] Device '{device}' non connecté actuellement. Skip.")
        return

    ws = session["ws"]
    loop = asyncio.new_event_loop()

    def on_chunk(text):
        try:
            asyncio.run_coroutine_threadsafe(
                ws.send_json({"type": "response_chunk", "text": text}),
                srv_main.app.state.main_loop,
            ).result(timeout=2)
        except Exception:
            pass

    def on_tool(name, _input, result):
        try:
            import json as _json
            asyncio.run_coroutine_threadsafe(
                ws.send_json({
                    "type": "tool_action", "tool": name,
                    "result": _json.loads(result) if isinstance(result, str) else result,
                }),
                srv_main.app.state.main_loop,
            ).result(timeout=2)
        except Exception:
            pass

    print(f"[briefing] → {device}")
    response, session["history"] = process_request_streaming(
        _briefing_prompt(),
        session["history"],
        on_text_delta=on_chunk,
        on_tool_call=on_tool,
        device_id=device,
    )
    # Final message pour clôturer le tour côté UI
    try:
        asyncio.run_coroutine_threadsafe(
            ws.send_json({"type": "response", "content": response}),
            srv_main.app.state.main_loop,
        ).result(timeout=2)
    except Exception:
        pass
    try:
        from server import session_store
        session_store.save_history(device, session["history"])
    except Exception:
        pass


def setup_default_jobs():
    """Enregistre le briefing matinal si activé dans .env."""
    if not _env_bool("BRIEFING_ENABLED", False):
        return
    h, m = _parse_time(get_env("BRIEFING_TIME", "08:00") or "08:00", (8, 0))
    weekdays = _parse_weekdays(get_env("BRIEFING_WEEKDAYS"))
    SCHEDULER.register_job({
        "id": "morning_briefing",
        "schedule": {"hour": h, "minute": m, "weekdays": weekdays},
        "enabled": True,
        "fn": _run_morning_briefing,
    })
