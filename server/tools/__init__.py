"""
Agrégation des handlers de tous les tools Orion.
ALL_HANDLERS est consommé par l'orchestrateur pour router un tool_use Claude
vers la bonne fonction Python.
"""
from .file_manager import HANDLERS as _FILE_HANDLERS
from .code_runner import HANDLERS as _CODE_HANDLERS
from .web_search import HANDLERS as _WEB_HANDLERS
from .app_launcher import HANDLERS as _APP_HANDLERS
from .notifications import HANDLERS as _NOTIF_HANDLERS
from .screenshot import HANDLERS as _SCREEN_HANDLERS
from .documents import HANDLERS as _DOC_HANDLERS
from .automation import HANDLERS as _AUTO_HANDLERS
from .termux_mobile import HANDLERS as _TERMUX_HANDLERS
from .vision import HANDLERS as _VISION_HANDLERS
from .audit_query import HANDLERS as _AUDIT_HANDLERS
from server.safety_backup import HANDLERS as _BACKUP_HANDLERS

# Tools optionnels (dépendances lourdes ou configurables) : import tolérant
def _optional(module_name: str) -> dict:
    try:
        mod = __import__(f"server.tools.{module_name}", fromlist=["HANDLERS"])
        return getattr(mod, "HANDLERS", {})
    except ImportError:
        return {}

_GOOGLE_HANDLERS = _optional("google_workspace")
_IMAGE_HANDLERS = _optional("image_gen")

# Tools mémoire RAG (charge sentence-transformers au premier appel, pas à l'import)
try:
    from server.memory.rag_tools import HANDLERS as _MEMORY_HANDLERS
except ImportError:
    _MEMORY_HANDLERS = {}

ALL_HANDLERS = {
    **_FILE_HANDLERS,
    **_CODE_HANDLERS,
    **_WEB_HANDLERS,
    **_APP_HANDLERS,
    **_NOTIF_HANDLERS,
    **_SCREEN_HANDLERS,
    **_DOC_HANDLERS,
    **_AUTO_HANDLERS,
    **_TERMUX_HANDLERS,
    **_VISION_HANDLERS,
    **_AUDIT_HANDLERS,
    **_BACKUP_HANDLERS,
    **_GOOGLE_HANDLERS,
    **_IMAGE_HANDLERS,
    **_MEMORY_HANDLERS,
}
