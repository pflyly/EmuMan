import os
import shutil
from pathlib import Path

from app.utils.logger import get_logger
logger = get_logger(__name__)
from app.core.firmware_manager import FirmwareManager

class ModManager:
    """Manager for Game Mods (LayeredFS)"""

    @staticmethod
    def get_load_dir(eden_exe_path=None):
        """Get the 'load' directory for mods."""
        user_data = FirmwareManager.get_user_data_path(eden_exe_path)
        if user_data:
            return user_data / "load"
        return None

    @staticmethod
    def list_mods(eden_exe_path=None):
        """
        List all detected mods.
        Returns: { title_id: [ {name, enabled, path} ] }
        """
        load_dir = ModManager.get_load_dir(eden_exe_path)
        if not load_dir or not load_dir.exists():
            return {}

        mods = {}
        # Structure: load/TITLE_ID/MOD_NAME
        for title_id_path in load_dir.iterdir():
            if title_id_path.is_dir():
                title_id = title_id_path.name
                mods[title_id] = []
                
                for mod_path in title_id_path.iterdir():
                    if mod_path.is_dir():
                        name = mod_path.name
                        enabled = not name.endswith(".disabled")
                        
                        # Display name cleans up the suffix
                        display_name = name.replace(".disabled", "")
                        
                        mods[title_id].append({
                            "name": display_name,
                            "enabled": enabled,
                            "path": mod_path
                        })
                        
        return mods

    @staticmethod
    def toggle_mod(mod_path_str, enable):
        """
        Enable/Disable a mod by renaming.
        """
        try:
            path = Path(mod_path_str)
            if not path.exists():
                return False, "Mod path not found"
            
            parent = path.parent
            name = path.name
            
            if enable:
                if not name.endswith(".disabled"): return True, "Already enabled"
                new_name = name.replace(".disabled", "")
            else:
                if name.endswith(".disabled"): return True, "Already disabled"
                new_name = name + ".disabled"
                
            new_path = parent / new_name
            path.rename(new_path)
            logger.info(f"Toggled mod: {path} -> {new_path}")
            return True, new_path
        except Exception as e:
            logger.error(f"Failed to toggle mod: {e}")
            return False, str(e)

    @staticmethod
    def open_mod_folder(eden_exe_path=None):
        load_dir = ModManager.get_load_dir(eden_exe_path)
        if load_dir:
            load_dir.mkdir(parents=True, exist_ok=True)
            return load_dir
        return None
