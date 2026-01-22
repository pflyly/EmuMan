import os
import shutil
from pathlib import Path

from app.utils.logger import get_logger
logger = get_logger(__name__)
from app.core.firmware_manager import FirmwareManager

class KeysManager:
    """Manager for prod.keys and title.keys"""

    @staticmethod
    def get_keys_dir(eden_exe_path=None):
        """Get the directory where keys should be stored."""
        user_data = FirmwareManager.get_user_data_path(eden_exe_path)
        if user_data:
            return user_data / "keys"
        return None

    @staticmethod
    def get_key_status(eden_exe_path=None):
        """
        Check status of keys.
        Returns: { 'prod.keys': bool, 'title.keys': bool, 'path': Path }
        """
        keys_dir = KeysManager.get_keys_dir(eden_exe_path)
        status = {
            'prod.keys': False,
            'title.keys': False,
            'path': str(keys_dir) if keys_dir else ""
        }
        
        if keys_dir and keys_dir.exists():
            status['prod.keys'] = (keys_dir / "prod.keys").exists()
            status['title.keys'] = (keys_dir / "title.keys").exists()
            
        return status

    @staticmethod
    def import_key_file(source_path, eden_exe_path=None):
        """
        Import a key file (prod.keys or title.keys).
        """
        keys_dir = KeysManager.get_keys_dir(eden_exe_path)
        if not keys_dir:
            return False, "Unable to resolve keys directory"
            
        try:
            keys_dir.mkdir(parents=True, exist_ok=True)
            source = Path(source_path)
            if not source.exists():
                return False, "Source file does not exist"
                
            dest = keys_dir / source.name
            shutil.copy2(source, dest)
            logger.info(f"Imported key file: {source} -> {dest}")
            return True, f"Successfully imported {source.name}"
            
        except Exception as e:
            logger.error(f"Failed to import key: {e}")
            return False, str(e)

    @staticmethod
    def auto_detect_keys():
        """
        Scan common emulator directories for keys.
        Returns: List of found key file paths.
        """
        candidates = []
        roaming = Path(os.getenv('APPDATA')) if os.name == 'nt' else Path.home() / ".config"
        
        # Common paths for Yuzu/Ryujinx
        search_paths = [
            roaming / "yuzu" / "keys",
            roaming / "Ryujinx" / "system",
            roaming / "suyu" / "keys",
        ]
        
        found_files = []
        for p in search_paths:
            if p.exists():
                for k in ["prod.keys", "title.keys"]:
                    kp = p / k
                    if kp.exists():
                        found_files.append(kp)
                        
        return found_files
