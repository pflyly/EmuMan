import os
import sys
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import requests
from PySide6.QtCore import QThread, Signal

from app.utils.logger import get_logger
logger = get_logger(__name__)

class DownloadThread(QThread):
    progress = Signal(int, str) # percent, speed_str
    finished = Signal(bool, str)
    cancelled = Signal()

    def __init__(self, url, save_path):
        super().__init__()
        self.url = url
        self.save_path = save_path
        self._is_running = True
    
    def stop(self):
        self._is_running = False

    def run(self):
        logger.info(f"Starting download: {self.url} -> {self.save_path}")
        try:
            def progress_cb(phase, current, total, speed=""):
                if self._is_running:
                    self.progress.emit(current, speed)
            
            def cancel_check():
                return not self._is_running
            
            success = Downloader.download(self.url, self.save_path, progress_cb, cancel_check)
            
            if not self._is_running:
                self.cancelled.emit()
                return

            if success:
                self.finished.emit(True, self.save_path)
            else:
                self.finished.emit(False, "Download failed")
                
        except Exception as e:
            self.finished.emit(False, str(e))

class Downloader:
    """
    Unified Downloader utility.
    Prioritizes Aria2c for multi-threaded downloads, falls back to requests.
    Respects 'downloader_type' in config.json.
    """
    
    @staticmethod
    def get_aria2_executable():
        """Get path to aria2c executable, handling both dev and frozen environments."""
        # 1. Check system path
        if shutil.which("aria2c"):
            return "aria2c"
        
        # 2. Check bundled resources
        # If frozen (PyInstaller), resources are usually extracted to sys._MEIPASS
        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path.cwd()
            
        exe_name = "aria2c.exe" if sys.platform == "win32" else "aria2c"
        bundled = base_path / "resources" / "bin" / exe_name
        
        if bundled.exists():
            # Linux: Ensure executable permission
            if sys.platform != "win32" and not os.access(bundled, os.X_OK):
                try:
                    os.chmod(bundled, 0o755)
                    logger.info(f"Granted executable permission to {bundled}")
                except Exception as e:
                    logger.warning(f"Failed to chmod {bundled}: {e}")
            return str(bundled)
            
        return None

    @staticmethod
    def format_speed(bytes_per_sec):
        """Helper to format bytes/sec into human readable string."""
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.1f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec/1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec/(1024*1024):.1f} MB/s"

    @staticmethod
    def download(url, dest_path, progress_callback=None, cancel_check=None):
        """
        Download a file to dest_path.
        
        Args:
            url (str): Download URL
            dest_path (str|Path): Destination file path
            progress_callback (callable, optional): func(phase, current, total, speed). phase='download'
            cancel_check (callable, optional): func() -> bool. Returns True to cancel.
            
        Returns:
            bool: Success
        """
        dest_path = Path(dest_path)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check Config
        use_aria2 = True
        try:
            if os.path.exists("config.json"):
                with open("config.json", 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if config.get("downloader_type") == "requests":
                        use_aria2 = False
        except Exception as e:
            logger.warning(f"Error reading config for downloader preference: {e}")

        # Try Aria2 First
        if use_aria2 and Downloader.get_aria2_executable():
            try:
                if Downloader._download_aria2(url, dest_path, progress_callback, cancel_check):
                    return True
                
                # If cancelled, do not fallback
                if cancel_check and cancel_check():
                    return False
            except Exception as e:
                logger.warning(f"Aria2 download failed, falling back to internal: {e}")
        
        # Fallback to Requests
        logger.info("Using internal downloader (requests)...")
        return Downloader._download_requests(url, dest_path, progress_callback, cancel_check)

    @staticmethod
    def _download_aria2(url, dest_path, progress_callback, cancel_check):
        aria2c_path = Downloader.get_aria2_executable()
        dest_dir = dest_path.parent
        filename = dest_path.name
        # Build Aria2 command
        # Read user preferences for log level
        console_log_level = "warn"  # Default
        try:
            if os.path.exists("config.json"):
                import json
                with open("config.json", 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    if cfg.get("aria2_verbose_log", False):
                        console_log_level = "info"
                        logger.info("Aria2 verbose logging enabled (info level)")
        except Exception as e:
            logger.warning(f"Failed to read aria2_verbose_log setting: {e}")
        
        cmd = [
            aria2c_path,
            url,
            "-d", str(dest_path.parent),
            "-o", dest_path.name,
            "-j", "8",
            "-x", "8",
            "-s", "8",
            "-k", "1M",
            "--check-certificate=false",
            f"--console-log-level={console_log_level}",
            "--summary-interval=1",
            "--allow-overwrite=true"
        ]
        
        # Check if user wants to disable IPv6
        try:
            if os.path.exists("config.json"):
                import json
                with open("config.json", 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    if cfg.get("disable_ipv6", False):
                        cmd.append("--disable-ipv6=true")
                        logger.info("IPv6 disabled for Aria2 as per user setting")
        except Exception as e:
            logger.warning(f"Failed to read disable_ipv6 setting: {e}")
        
        logger.info(f"Starting Aria2 download: {' '.join(cmd)}")
        
        process = None
        try:
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='ignore',
                bufsize=1,
                startupinfo=startupinfo
            )
            
            # Progress regex: [#2b610d 0.9MiB/1.5MiB(58%) CN:1 DL:3.5MiB ETA:1s]
            # Capture percent and DL speed (DL:...)
            progress_pattern = re.compile(r'\((\d+)%\).*?DL:([0-9.]+[a-zA-Z]+)')
            
            last_lines = []
            
            while True:
                if cancel_check and cancel_check():
                    logger.info("Cancelling Aria2 download...")
                    
                    # Terminate the process
                    try:
                        process.kill()
                        process.wait(timeout=2)
                        logger.info("Aria2 process killed successfully")
                    except Exception as e:
                        logger.warning(f"Error killing Aria2 process: {e}")
                    
                    # Wait for Windows to release file handles
                    time.sleep(0.3)
                    
                    # Cleanup both .aria2 control file and partial download file
                    aria2_control_file = str(dest_path) + ".aria2"
                    files_to_remove = [aria2_control_file, str(dest_path)]
                    
                    for file_path in files_to_remove:
                        if not os.path.exists(file_path):
                            continue
                            
                        # Retry mechanism for file deletion
                        deleted = False
                        for attempt in range(3):
                            try:
                                os.remove(file_path)
                                logger.info(f"Cleaned up: {file_path}")
                                deleted = True
                                break
                            except PermissionError:
                                if attempt < 2:
                                    time.sleep(0.2)
                                else:
                                    logger.warning(f"Failed to remove {file_path} after {attempt + 1} attempts: file is locked")
                            except Exception as e:
                                logger.warning(f"Failed to remove {file_path}: {e}")
                                break
                    
                    return False
                
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                
                if output:
                    last_lines.append(output.strip())
                    if len(last_lines) > 20: last_lines.pop(0) # Keep last 20 lines
                    
                    # Log Aria2 output in real-time if verbose logging is enabled
                    if console_log_level in ("info", "debug"):
                        logger.info(f"[Aria2] {output.strip()}")
                    
                    match = progress_pattern.search(output)
                    if match and progress_callback:
                        try:
                            percent = int(match.group(1))
                            speed = match.group(2) + "/s"
                            progress_callback('download', percent, 100, speed)
                        except: pass
            
            if process.returncode == 0:
                if progress_callback: progress_callback('download', 100, 100, "")
                return True
            
            logger.error(f"Aria2 exited with code {process.returncode}")
            logger.error(f"Aria2 output snippet:\n" + "\n".join(last_lines))
            return False
            
        except Exception as e:
            logger.error(f"Aria2 execution error: {e}")
            if process:
                try: 
                    process.kill()
                    process.wait(timeout=1)
                except: pass
            raise e

    @staticmethod
    def _download_requests(url, dest_path, progress_callback, cancel_check):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            start_time = time.time()
            last_speed_update = start_time
            
            with open(dest_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024*64):
                    if cancel_check and cancel_check():
                        logger.info("Cancelling requests download...")
                        # File will be closed by context manager
                        # Then cleanup the partial file
                        f.close()
                        if os.path.exists(dest_path):
                            try:
                                os.remove(dest_path)
                                logger.info(f"Cleaned up partial download: {dest_path}")
                            except Exception as e:
                                logger.warning(f"Failed to remove partial file: {e}")
                        return False
                        
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    current_time = time.time()
                    if progress_callback and total_size > 0:
                        # Calculate speed every ~0.5s or so? Or just every chunk? 
                        # Chunk is 64KB, might be too jittery. 
                        # Use average since start for simplicity or windowed?
                        # Let's use average since start for valid speed or simple window.
                        # Simple window:
                        speed_str = ""
                        if current_time - last_speed_update > 0.5:
                            duration = current_time - start_time
                            if duration > 0:
                                speed = downloaded / duration
                                speed_str = Downloader.format_speed(speed)
                                # Consider updating last_speed_update mechanism if we want instantaneous speed
                                # But simple average is robust enough for simple fallback
                        
                        progress_callback('download', int(downloaded / total_size * 100), 100, speed_str)
            
            if progress_callback: progress_callback('download', 100, 100, "")
            return True
            
        except Exception as e:
            logger.error(f"Internal download failed: {e}")
            # Cleanup partial file on error
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                    logger.info(f"Cleaned up failed download: {dest_path}")
                except:
                    pass
            return False
