"""
Orion Tool — Web Search & Fetch
Recherche sur le web via DuckDuckGo (gratuit, sans clé API).
Optionnel : Brave Search API si configuré.
"""
import os
import urllib.parse
import urllib.request
import json
import re


def _duckduckgo_search(query: str, max_results: int = 5) -> list:
    """Recherche via l'API DuckDuckGo Instant Answer (gratuite)."""
    encoded = urllib.parse.quote(query)
    url = f"https://api.duckduckgo.com/?q={encoded}&format=json&no_html=1&skip_disambig=1"

    req = urllib.request.Request(url, headers={"User-Agent": "Orion/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())

    results = []

    # Abstract (réponse directe)
    if data.get("AbstractText"):
        results.append({
            "title": data.get("Heading", query),
            "snippet": data["AbstractText"],
            "url": data.get("AbstractURL", ""),
            "source": data.get("AbstractSource", ""),
        })

    # RelatedTopics
    for topic in data.get("RelatedTopics", []):
        if isinstance(topic, dict) and topic.get("Text"):
            results.append({
                "title": topic.get("Text", "")[:80],
                "snippet": topic.get("Text", ""),
                "url": topic.get("FirstURL", ""),
                "source": "DuckDuckGo",
            })
        if len(results) >= max_results:
            break

    return results


def _brave_search(query: str, max_results: int = 5, api_key: str = "") -> list:
    """Recherche via Brave Search API (meilleure qualité, clé requise)."""
    encoded = urllib.parse.quote(query)
    url = f"https://api.search.brave.com/res/v1/web/search?q={encoded}&count={max_results}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())

    results = []
    for item in data.get("web", {}).get("results", [])[:max_results]:
        results.append({
            "title": item.get("title", ""),
            "snippet": item.get("description", ""),
            "url": item.get("url", ""),
            "source": "Brave",
        })
    return results


def web_search(query: str, max_results: int = 5) -> dict:
    """Point d'entrée principal pour la recherche web."""
    brave_key = os.getenv("BRAVE_API_KEY", "")
    try:
        if brave_key:
            results = _brave_search(query, max_results, brave_key)
        else:
            results = _duckduckgo_search(query, max_results)

        if not results:
            return {
                "success": True,
                "query": query,
                "results": [],
                "message": "Aucun résultat trouvé. Essaie une formulation différente.",
            }
        return {"success": True, "query": query, "results": results}
    except Exception as e:
        return {"success": False, "error": f"Erreur recherche : {str(e)}"}


def fetch_url(url: str, max_chars: int = 5000) -> dict:
    """Récupère le contenu texte d'une URL."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Orion/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read().decode("utf-8", errors="replace")

        # Nettoyage HTML basique
        clean = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<style[^>]*>.*?</style>", "", clean, flags=re.DOTALL | re.IGNORECASE)
        clean = re.sub(r"<[^>]+>", " ", clean)
        clean = re.sub(r"\s+", " ", clean).strip()

        return {"success": True, "url": url, "content": clean[:max_chars], "truncated": len(clean) > max_chars}
    except Exception as e:
        return {"success": False, "error": str(e)}


HANDLERS = {
    "web_search": lambda p: web_search(**p),
    "fetch_url": lambda p: fetch_url(**p),
}
