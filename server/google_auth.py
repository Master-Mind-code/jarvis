"""
Helper OAuth Google partagé par les tools Gmail / GCalendar.

Setup utilisateur (une fois) :
  1. Aller sur https://console.cloud.google.com/apis/credentials
  2. Créer un projet, activer l'API Gmail et l'API Google Calendar
  3. Créer un OAuth 2.0 Client ID de type "Desktop app"
  4. Télécharger credentials.json → le placer dans data/google/credentials.json
  5. Au premier appel d'un tool Google, un navigateur s'ouvre pour autoriser :
     le token est stocké dans data/google/token.json (refresh automatique ensuite)

Variables d'env (toutes optionnelles) :
  ORION_GOOGLE_CREDENTIALS  chemin vers credentials.json (défaut: data/google/credentials.json)
  ORION_GOOGLE_TOKEN        chemin vers token.json      (défaut: data/google/token.json)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from branding import get_env

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "google"

# Scopes lus + écrits. read-only par défaut, write activé pour Calendar create.
SCOPES_GMAIL_READ = ["https://www.googleapis.com/auth/gmail.readonly"]
SCOPES_CALENDAR_RW = ["https://www.googleapis.com/auth/calendar"]

# Scopes combinés : un seul flow OAuth couvre tous les tools Orion
ORION_SCOPES = sorted(set(SCOPES_GMAIL_READ + SCOPES_CALENDAR_RW))


def _credentials_path() -> Path:
    raw = get_env("GOOGLE_CREDENTIALS") or str(DEFAULT_DIR / "credentials.json")
    return Path(raw)


def _token_path() -> Path:
    raw = get_env("GOOGLE_TOKEN") or str(DEFAULT_DIR / "token.json")
    return Path(raw)


def _import_google_libs():
    """Import paresseux pour ne pas forcer la dépendance si Google n'est pas utilisé."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise ImportError(
            "Les dépendances Google ne sont pas installées. Installe avec :\n"
            "    pip install google-api-python-client google-auth-httplib2 "
            "google-auth-oauthlib"
        ) from exc
    return Request, Credentials, InstalledAppFlow, build


def get_credentials(scopes: Iterable[str] = ORION_SCOPES):
    """Retourne des Credentials valides, en lançant le flow OAuth au besoin.

    Refresh automatique si un refresh_token est disponible.
    """
    Request, Credentials, InstalledAppFlow, _ = _import_google_libs()

    token_path = _token_path()
    creds_path = _credentials_path()
    scopes_list = list(scopes)

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes_list)
        except Exception:
            creds = None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    if not creds_path.exists():
        raise FileNotFoundError(
            f"credentials.json introuvable à {creds_path}.\n"
            "Télécharge-le depuis https://console.cloud.google.com/apis/credentials "
            "(OAuth 2.0 Client ID, type Desktop app) puis place-le à cet emplacement.\n"
            "Active aussi les APIs Gmail et Google Calendar dans le projet GCP."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), scopes_list)
    # Lance le serveur de callback local et ouvre le navigateur
    creds = flow.run_local_server(port=0, prompt="consent")
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    print(f"[google] Token sauvegardé dans {token_path}")
    return creds


def gmail_service():
    _, _, _, build = _import_google_libs()
    return build("gmail", "v1", credentials=get_credentials(SCOPES_GMAIL_READ),
                 cache_discovery=False)


def calendar_service():
    _, _, _, build = _import_google_libs()
    return build("calendar", "v3", credentials=get_credentials(SCOPES_CALENDAR_RW),
                 cache_discovery=False)


def google_setup_status() -> dict:
    """Diagnostic : indique ce qui est en place ou manquant."""
    return {
        "credentials_path": str(_credentials_path()),
        "credentials_exists": _credentials_path().exists(),
        "token_path": str(_token_path()),
        "token_exists": _token_path().exists(),
    }
