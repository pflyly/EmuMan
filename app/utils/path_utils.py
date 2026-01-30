import os
import sys
import subprocess
import platform
import shutil

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

from app.utils.logger import get_logger
logger = get_logger(__name__)

def open_directory(path):
    """
    Open the directory in the default file manager.
    Platform-independent implementation.
    """
    if not os.path.exists(path):
        return False, f"Path not found: {path}"
        
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            # Linux/Unix
            # Prioritize Dolphin (Steam Deck/KDE)
            commands = ["dolphin", "xdg-open", "nautilus", "nemo", "thunar", "pcmanfm", "caja"]
            success = False
            last_error = ""
            
            for cmd in commands:
                if shutil.which(cmd):
                    logger.info(f"Attempting to open directory with: {cmd}")
                    try:
                        # Sanitize environment for Linux subprocesses to prevent PyInstaller lib conflicts
                        env = os.environ.copy()
                        
                        # 1. Restore LD_LIBRARY_PATH
                        if 'LD_LIBRARY_PATH_ORIG' in env:
                            env['LD_LIBRARY_PATH'] = env['LD_LIBRARY_PATH_ORIG']
                        elif 'LD_LIBRARY_PATH' in env:
                             # If ORIG is not set (rare in PyInstaller), unset it to be safe
                             del env['LD_LIBRARY_PATH']

                        # 2. Clean Qt-specific variables (Critical for launching system Qt apps like Dolphin)
                        for key in list(env.keys()):
                            if key.startswith("QT_") or key.startswith("PYTHON"):
                                del env[key]

                        # Use Popen. Wait shortly to check for immediate failure?
                        # xdg-open often returns immediately.
                        subprocess.Popen([cmd, path], stderr=subprocess.PIPE, env=env)
                        success = True
                        logger.info(f"Successfully launched {cmd}")
                        break
                    except Exception as e:
                        last_error = str(e)
                        logger.warning(f"Failed to launch {cmd}: {e}")
            
            if not success:
                return False, f"No suitable file manager found. Last error: {last_error}"
                
        return True, "Opened successfully"
    except Exception as e:
        logger.error(f"open_directory failed: {e}")
        return False, str(e)
