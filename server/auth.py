"""
Tokens d'auth Orion par scope.

3 scopes possibles :
    USER     : sessions chat (UI navigateur, voice, controller). Lecture + écriture chat.
    WORKER   : RPC entre serveur et workers distants. PAS d'accès au chat ni à l'admin.
    ADMIN    : endpoints critiques (/api/panic, /api/audit, /devices, transcribe).
               Inclut implicitement USER + WORKER.

Configuration :
    ORION_SECRET_TOKEN=...    (legacy : fallback global pour les 3 scopes)
    ORION_TOKEN_USER=...      (override scope USER)
    ORION_TOKEN_WORKER=...    (override scope WORKER)
    ORION_TOKEN_ADMIN=...     (override scope ADMIN)

Si seul SECRET_TOKEN est défini → mode compat, ce token vaut pour tous les scopes.
Si TOKEN_USER + TOKEN_WORKER + TOKEN_ADMIN sont définis → 3 tokens distincts,
plus sûr (compromission d'un scope = pas accès aux autres).
"""
from __future__ import annotations

from branding import get_env, DEFAULT_SECRET_TOKEN

USER = "user"
WORKER = "worker"
ADMIN = "admin"


def _legacy_token() -> str:
    return (get_env("SECRET_TOKEN") or "").strip() or DEFAULT_SECRET_TOKEN


def expected(scope: str) -> str:
    """Retourne le token attendu pour ce scope, avec fallback sur SECRET_TOKEN."""
    direct = (get_env(f"TOKEN_{scope.upper()}") or "").strip()
    if direct:
        return direct
    return _legacy_token()


def verify(scope: str, token: str | None) -> bool:
    """True si le token fourni correspond au scope demandé.

    L'ADMIN peut tout faire (vérifie aussi USER et WORKER).
    """
    if not token:
        return False
    token = token.strip()
    if not token:
        return False

    # Le token ADMIN passe pour tous les scopes
    admin_token = expected(ADMIN)
    if token == admin_token:
        return True

    # Sinon, on demande la correspondance exacte du scope demandé
    return token == expected(scope)


def status() -> dict:
    """Diagnostic non secret : quels scopes ont un token séparé ?"""
    legacy = _legacy_token()
    out = {}
    for s in (USER, WORKER, ADMIN):
        direct = (get_env(f"TOKEN_{s.upper()}") or "").strip()
        out[s] = {
            "configured": bool(direct),
            "uses_legacy_fallback": not direct,
            "matches_legacy": direct == legacy if direct else True,
        }
    out["legacy_token_present"] = bool(legacy and legacy != DEFAULT_SECRET_TOKEN)
    out["mode"] = (
        "scoped"
        if all(get_env(f"TOKEN_{s.upper()}") for s in (USER, WORKER, ADMIN))
        else "single (legacy)"
    )
    return out
