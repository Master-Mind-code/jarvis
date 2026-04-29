"""
Jarvis Tool — Code Runner & Shell Executor
Exécuter des commandes shell et des scripts Python.
"""
import subprocess
import sys
import tempfile
import os
from pathlib import Path


# Commandes/patterns dangereux bloqués par défaut
BLOCKED_PATTERNS = [
    "rm -rf /", "rm -rf ~", "mkfs", "dd if=",
    ":(){:|:&};:", "chmod -R 777 /",
]


def _is_dangerous(cmd: str) -> bool:
    cmd_lower = cmd.lower().strip()
    return any(p in cmd_lower for p in BLOCKED_PATTERNS)


def run_shell_command(command: str, cwd: str = None, timeout: int = 30) -> dict:
    """Exécute une commande shell."""
    if _is_dangerous(command):
        return {"success": False, "error": "Commande potentiellement dangereuse bloquée. Sois plus précis."}

    work_dir = cwd or str(Path.home())

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:4000] if result.stdout else "",
            "stderr": result.stderr[:2000] if result.stderr else "",
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout dépassé ({timeout}s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_python_script(code: str, timeout: int = 30) -> dict:
    """Exécute du code Python dans un fichier temporaire."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[:4000],
            "stderr": result.stderr[:2000],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout ({timeout}s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        os.unlink(tmp_path)


def get_system_info() -> dict:
    """Retourne des infos basiques sur le système."""
    import platform
    return {
        "success": True,
        "os": platform.system(),
        "os_version": platform.version(),
        "python": sys.version,
        "home": str(Path.home()),
        "cwd": os.getcwd(),
    }


HANDLERS = {
    "run_shell_command": lambda p: run_shell_command(**p),
    "run_python_script": lambda p: run_python_script(**p),
    "get_system_info": lambda p: get_system_info(),
}
