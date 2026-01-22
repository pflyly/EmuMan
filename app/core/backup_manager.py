import os
import time
import shutil
import zipfile
from pathlib import Path

from app.utils.logger import get_logger
logger = get_logger(__name__)

from app.core.firmware_manager import FirmwareManager

class BackupManager:
    """Manages creation and restoration of save data backups."""
    
    @staticmethod
    def get_save_dir(eden_exe_path=None):
        """Resolve the active save directory."""
        user_data = FirmwareManager.get_user_data_path(eden_exe_path)
        if user_data:
            return user_data / "nand" / "user" / "save"
        return None

    @staticmethod
    def get_backup_root():
        """Ensure and return the root backup directory."""
        root = Path("backups") / "saves"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @staticmethod
    def create_backup(eden_exe_path=None, note=""):
        """
        Compress the save directory into a zip archive.
        Returns: (success, message_or_path)
        """
        save_dir = BackupManager.get_save_dir(eden_exe_path)
        if not save_dir or not save_dir.exists():
            return False, "Save directory not found"
        
        # Check if empty (optional, but good to know)
        if not any(save_dir.iterdir()):
            return False, "Save directory is empty"

        try:
            timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"save_backup_{timestamp}.zip"
            if note:
                filename = f"save_backup_{timestamp}_{note}.zip"
            
            backup_path = BackupManager.get_backup_root() / filename
            
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                for file in save_dir.rglob('*'):
                    if file.is_file():
                        arcname = file.relative_to(save_dir)
                        zf.write(file, arcname)
                        
            logger.info(f"Backup created: {backup_path}")
            return True, str(backup_path)
            
        except Exception as e:
            logger.error(f"Backup failed: {e}")
            return False, str(e)

    @staticmethod
    def restore_backup(zip_path, eden_exe_path=None):
        """
        Restore a backup.
        WARNING: This overwrites/deletes current saves.
        """
        save_dir = BackupManager.get_save_dir(eden_exe_path)
        if not save_dir:
            return False, "Save directory location cannot be determined"
            
        if not os.path.exists(zip_path):
            return False, "Backup file not found"
            
        try:
            # 1. Safety Backup (Overwrite Protection) - Optional, simpler to just clean for now
            # But let's at least ensure the dir exists
            save_dir.mkdir(parents=True, exist_ok=True)
            
            # 2. Clean current saves
            for item in save_dir.iterdir():
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception: pass
                
            # 3. Extract
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(save_dir)
                
            logger.info(f"Restored backup {zip_path} to {save_dir}")
            return True, "Restored Successfully"
            
        except Exception as e:
            logger.error(f"Restore failed: {e}")
            return False, str(e)

    @staticmethod
    def get_backup_list():
        """
        Return list of backups [
            {'name': str, 'path': Path, 'time': float, 'size_str': str}
        ]
        """
        root = BackupManager.get_backup_root()
        backups = []
        
        for file in root.glob("*.zip"):
            try:
                stat = file.stat()
                size_mb = stat.st_size / (1024 * 1024)
                size_str = f"{size_mb:.2f} MB"
                if size_mb < 1:
                    size_str = f"{stat.st_size / 1024:.0f} KB"
                    
                backups.append({
                    "name": file.name,
                    "path": file,
                    "time": stat.st_mtime,
                    "size_str": size_str
                })
            except: pass
            
        # Sort by new
        return sorted(backups, key=lambda x: x['time'], reverse=True)

    @staticmethod
    def delete_backup(zip_path):
        try:
            os.remove(zip_path)
            logger.info(f"Deleted backup: {zip_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete backup {zip_path}: {e}")
            return False
