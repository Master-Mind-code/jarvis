"""
Agrégation des handlers de tous les tools Orion.
ALL_HANDLERS est consommé par l'orchestrateur pour router un tool_use Claude
vers la bonne fonction Python.
"""
from .file_manager import HANDLERS as _FILE_HANDLERS
from .code_runner import HANDLERS as _CODE_HANDLERS
from .web_search import HANDLERS as _WEB_HANDLERS
from .app_launcher import HANDLERS as _APP_HANDLERS

ALL_HANDLERS = {
    **_FILE_HANDLERS,
    **_CODE_HANDLERS,
    **_WEB_HANDLERS,
    **_APP_HANDLERS,
}
