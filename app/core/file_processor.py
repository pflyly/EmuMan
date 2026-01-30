import os
import sys
import zipfile
import stat
from PySide6.QtCore import QObject, Signal
from app.utils.downloader import DownloadThread

from app.utils.logger import get_logger
logger = get_logger(__name__)

class FileProcessor(QObject):
    """
    Handles file operations including downloading, extraction, and permission management.
    Now manages the download lifecycle to reduce UI complexity.
    """
    
    # Signals for UI updates
    download_progress = Signal(int, str)
    process_finished = Signal(bool, str, str, str)  # success, msg/path, branch, tag
    process_cancelled = Signal()
    manual_required = Signal(str) # path

    def __init__(self):
        super().__init__()
        self.dl_thread = None

    @staticmethod
    def is_debian_based():
        """Identify if the current Linux system is Debian/Ubuntu based."""
        if sys.platform == "win32": return False
        try:
            return os.path.exists("/etc/debian_version") or \
                   (os.path.exists("/etc/os-release") and "debian" in open("/etc/os-release").read().lower())
        except Exception:
            return False

    @staticmethod
    def fix_executable_permission(path):
        """Apply chmod +x to a specific file on Linux/Unix systems."""
        if sys.platform == "win32": return
        try:
            # Idempotency check: if already executable, skip
            if os.access(path, os.X_OK):
                return True
                
            logger.info(f"Linux: Applying executable permission to {path}")
            st = os.stat(path)
            os.chmod(path, st.st_mode | stat.S_IEXEC)
            return True
        except Exception as e:
            logger.warning(f"chmod failed for {path}: {e}")
            return False

    def start_download_task(self, url, save_path, branch, tag):
        """Starts the download thread and manages the workflow."""
        if self.dl_thread and self.dl_thread.isRunning():
            logger.warning("Download already in progress.")
            return

        self.dl_thread = DownloadThread(url, save_path)
        self.dl_thread.progress.connect(self.download_progress.emit)
        self.dl_thread.finished.connect(lambda ok, path: self._on_download_complete_internal(ok, path, branch, tag))
        
        # 绑定取消信号
        self.dl_thread.cancelled.connect(self.process_cancelled.emit)
        
        self.dl_thread.start()

    def cancel_download_task(self):
        """Cancels the current download task if running."""
        if self.dl_thread and self.dl_thread.isRunning():
            logger.info("Requesting download cancellation...")
            self.dl_thread.stop()

    def _on_download_complete_internal(self, ok, path, branch, tag):
        """Internal handler for download completion."""
        if not ok:
            self.process_finished.emit(False, path, branch, tag) # path is error msg here
            return

        # Success - Proceed to extraction
        result = self.process_archive(path, branch)
        
        if result == "manual_required":
            self.manual_required.emit(path)
        
        # Emit success (path is the downloaded file path)
        self.process_finished.emit(True, path, branch, tag)

    def process_archive(self, file_path, branch):
        """Determine target directory based on branch and extract."""
        extract_dir = os.path.dirname(file_path)
        
        # Master archives typically lack a top-level folder, so we create one to avoid mess
        if branch == "master":
            folder_name = os.path.splitext(os.path.basename(file_path))[0]
            target_dir = os.path.join(extract_dir, folder_name)
            os.makedirs(target_dir, exist_ok=True)
        else:
            # Nightly archives usually have their own structure or user prefers flat
            target_dir = extract_dir
            
        return self.extract_archive(file_path, target_dir)

    def extract_archive(self, file_path, target_dir):
        """Extract ZIP files and handle special instructions for 7z/Linux binaries."""
        filename_lower = file_path.lower()
        
        # 1. Linux binary/package skip extraction
        if filename_lower.endswith((".appimage", ".deb")):
            logger.info(f"Post-download: skipping extraction for Linux target {file_path}")
            self.fix_executable_permission(file_path)
            return "binary_preserved"

        # 2. Archive handling
        try:
            if file_path.endswith(".zip"):
                logger.info(f"Extracting ZIP: {file_path} -> {target_dir}")
                with zipfile.ZipFile(file_path, 'r') as z:
                    z.extractall(target_dir)
                
                # Check if user wants to keep the archive
                keep_archive = False
                try:
                    if os.path.exists("config.json"):
                        import json
                        with open("config.json", 'r', encoding='utf-8') as f:
                            cfg = json.load(f)
                            keep_archive = cfg.get("keep_archive", False)
                except Exception as e:
                    logger.warning(f"Failed to read keep_archive setting: {e}")
                
                # Delete archive if user preference is to not keep it
                if not keep_archive:
                    os.remove(file_path)
                    logger.info(f"Deleted archive: {file_path}")
                else:
                    logger.info(f"Kept archive as per user setting: {file_path}")
                
                # Cleanup: ensure extracted binaries are executable
                if sys.platform != "win32":
                    for root, _, files in os.walk(target_dir):
                        for f in files:
                            if f == "eden" or f.endswith(".AppImage"):
                                self.fix_executable_permission(os.path.join(root, f))
                return "extracted"
            
            elif file_path.endswith(".7z"):
                return "manual_required"
                
        except Exception as e:
            logger.error(f"Extraction failed for {file_path}: {e}")
            return "failed"
            
        return "unsupported"
