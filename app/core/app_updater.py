import os
import sys
import json
import time
import webbrowser
import subprocess

import requests
from PySide6.QtCore import QObject, Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QThread, Signal
from PySide6.QtGui import QColor
from qfluentwidgets import InfoBar, InfoBarPosition, MessageBox, FluentIcon as FIF

from app.config import CURRENT_VERSION
from app.utils.downloader import DownloadThread

from app.utils.logger import get_logger
logger = get_logger(__name__)

class UpdateCheckWorker(QThread):
    finished = Signal(bool, dict)

    def __init__(self, repo):
        super().__init__()
        self.repo = repo

    def run(self):
        url = f"https://api.github.com/repos/{self.repo}/releases/latest"
        headers = {'Accept': 'application/vnd.github.v3+json', 'User-Agent': 'EmuMan-App-Client'}
        
        try:
            res = requests.get(url, headers=headers, timeout=8)
            if res.status_code != 200:
                self.finished.emit(False, {})
                return
                
            data = res.json()
            result = {
                "tag": data.get("tag_name", ""),
                "html_url": data.get("html_url"),
                "exe_url": None,
                "exe_name": None
            }
            
            # Find compatible asset
            for asset in data.get("assets", []):
                name = asset['name'].lower()
                if sys.platform == "win32" and name.endswith(".exe"):
                    result["exe_url"] = asset['browser_download_url']
                    result["exe_name"] = asset['name']
                    break
                elif sys.platform == "linux" and ("linux" in name or name.endswith(".appimage")):
                    result["exe_url"] = asset['browser_download_url']
                    result["exe_name"] = asset['name']
                    break
            
            self.finished.emit(True, result)
            
        except Exception as e:
            logger.warning(f"Self-update check failed in worker: {e}")
            self.finished.emit(False, {})

class AppUpdater(QObject):
    """Encapsulates self-update logic including UI feedback, download flow and process replacement."""
    
    def __init__(self, repo="pflyly/EmuMan"):
        super().__init__()
        self.repo = repo
        self.latest_version = None
        self.update_exe_url = None
        self.update_exe_name = None
        self.html_url = None
        
        # UI References (weak injection)
        self.ui_badge = None
        self.ui_label = None
        self.ui_subtitle = None
        self.parent_win = None
        self.lang = {}
        
        self.anim = None
        self.new_app_path = None
        
        self.check_worker = None

    # =========================================
    #             Public API
    # =========================================

    def bind_ui(self, badge, label, subtitle, window, lang):
        """Bind UI components for feedback manipulation."""
        self.ui_badge = badge
        self.ui_label = label
        self.ui_subtitle = subtitle
        self.parent_win = window
        self.lang = lang

    def check_for_updates(self):
        """
        Check for updates via local cache or network (Async).
        Returns: (bool available, str version) -> Only for cache hit. Network result is async.
        """
        cache_path = os.path.join("cache", "app_cache.json")
        
        # 1. Try Local Cache
        cache_data = self._load_cache(cache_path)
        is_cache_valid = (time.time() - cache_data.get("timestamp", 0) < 86400)
        cached_version = cache_data.get("version")

        if is_cache_valid and cached_version:
            if cached_version != CURRENT_VERSION:
                self._apply_cached_data(cache_data)
                self._show_update_notice()
                return True, cached_version
            return False, None
        
        # 2. Start Async Network Check
        self.start_check_update_async()
        return False, None

    def start_check_update_async(self):
        if self.check_worker and self.check_worker.isRunning():
            return
            
        self.check_worker = UpdateCheckWorker(self.repo)
        self.check_worker.finished.connect(self._on_check_finished)
        self.check_worker.start()

    def _on_check_finished(self, success, data):
        cache_path = os.path.join("cache", "app_cache.json")
        
        if success:
            tag = data.get("tag")
            if tag and tag != CURRENT_VERSION:
                self._save_cache(cache_path, tag, data["html_url"], data["exe_url"], data["exe_name"])
                self.update_exe_url = data["exe_url"]
                self.update_exe_name = data["exe_name"]
                self.html_url = data["html_url"]
                self.latest_version = tag
                
                if not self.update_exe_url:
                    logger.warning(f"New version {tag} detected but no compatible binary found.")
                else:
                    logger.info(f"New EmuMan Available: {tag} -> {self.update_exe_name}")
                    
                self._show_update_notice()
            else:
                self._save_cache(cache_path, tag or CURRENT_VERSION, data["html_url"], None, None)
        else:
            # Network failed, check if we have stale cache to clear
            cache_data = self._load_cache(cache_path)
            is_cache_valid = (time.time() - cache_data.get("timestamp", 0) < 86400)
            if cache_data.get("version") and not is_cache_valid:
                 logger.info("Cache is stale and network failed. Clearing invalid cache.")
                 self._delete_cache(cache_path)

    def start_self_update(self):
        """Triggers the full confirmation -> download -> restart flow."""
        title = self.lang.get("update_app_title", "Software Update")
        content = self.lang.get("update_app_msg", "New version detected. Update and restart now?")
        
        if MessageBox(title, content, self.parent_win).exec():
            # Plan B: No direct download link -> Open browser
            if not self.update_exe_url:
                self.trigger_launch_web()
                return

            self._start_download_process()

    def trigger_launch_web(self):
        url = self.html_url if self.html_url else f"https://github.com/{self.repo}/releases"
        webbrowser.open(url)
        return True

    # =========================================
    #          Internal Core Logic
    # =========================================

    def _start_download_process(self):
        # 1. Prepare target path
        temp_dir = os.path.join(os.environ.get('TEMP', '.'), "EmuManUpdate") if sys.platform == "win32" else "/tmp/EmuManUpdate"
        os.makedirs(temp_dir, exist_ok=True)
        self.new_app_path = os.path.join(temp_dir, self.update_exe_name)
        
        # 2. Show Progress InfoBar
        self.dl_info = InfoBar.info(
            title=self.lang.get("downloading", "Downloading update..."),
            content=self.update_exe_name,
            orient=Qt.Horizontal,
            isClosable=False,
            position=InfoBarPosition.TOP,
            duration=-1,
            parent=self.parent_win
        )
        
        # 3. Start Download
        self.thread = DownloadThread(self.update_exe_url, self.new_app_path)
        self.thread.progress.connect(lambda p, s="": self.dl_info.titleLabel.setText(f"{self.lang.get('downloading')}: {p}%" + (f" - {s}" if s else "")))
        self.thread.finished.connect(self._on_download_complete)
        self.thread.start()

    def _on_download_complete(self, success, msg):
        if hasattr(self, 'dl_info') and self.dl_info:
            self.dl_info.close()
            
        if not success:
            InfoBar.error("Update Failed", f"Unable to download: {msg}", parent=self.parent_win)
            if MessageBox("Update Error", "Download failed. Open releases page to upgrade manually?", self.parent_win).exec():
                self.trigger_launch_web()
            return
            
        self._apply_update_and_restart()

    def _apply_update_and_restart(self):
        """Perform system-specific file replacement and application restart."""
        if not getattr(sys, 'frozen', False):
            MessageBox("Dev Mode", f"New version downloaded to:\n{self.new_app_path}\n\nUpdate skipped in dev mode.", self.parent_win).exec()
            return
            
        current_path = os.path.abspath(sys.argv[0])
        new_exe = os.path.abspath(self.new_app_path)
        logger.info(f"Applying App update: {new_exe} -> {current_path}")
        
        try:
            if sys.platform == "win32":
                cmd = f'chcp 65001 && ping 127.0.0.1 -n 3 > nul && move /y "{new_exe}" "{current_path}" && start "" "{current_path}"'
                subprocess.Popen(cmd, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS)
            else:
                cmd = f'sleep 2 && mv -f "{new_exe}" "{current_path}" && chmod +x "{current_path}" && "{current_path}" &'
                subprocess.Popen(cmd, shell=True, preexec_fn=getattr(os, 'setpgrp', None))
                
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
            
        except Exception as e:
            logging.critical(f"Update restart failed: {e}")

    # =========================================
    #             UI Helpers
    # =========================================

    def _show_update_notice(self):
        """Display icon/labels and start animations on the UI."""
        if not self.ui_badge: return
        
        self.ui_badge.setIcon(FIF.CLOUD_DOWNLOAD.icon(color=QColor("#ff4757")))
        self.ui_badge.show()
        QTimer.singleShot(200, self._start_badge_animation)
        
        if self.ui_label:
            self.ui_label.setText(f"← {self.latest_version}")
            self.ui_label.show()
            
        if self.ui_subtitle:
            self.ui_subtitle.setStyleSheet("CaptionLabel { color: rgba(128, 128, 128, 150); }")

    def _start_badge_animation(self):
        """Restore the bouncy animation for the update badge."""
        if not self.ui_badge: return
        
        self.anim = QPropertyAnimation(self.ui_badge, b"pos")
        self.anim.setDuration(1300)
        
        curr_pos = self.ui_badge.pos()
        self.anim.setStartValue(curr_pos)
        self.anim.setEndValue(QPoint(curr_pos.x(), curr_pos.y() - 5))
        
        self.anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.anim.setLoopCount(-1)
        self.anim.start()

    # =========================================
    #            Cache Helpers
    # =========================================

    def _load_cache(self, cache_path):
        if not os.path.exists(cache_path): return {}
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception: return {}

    def _save_cache(self, cache_path, version, html_url, download_url, filename):
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            data = {
                "version": version,
                "html_url": html_url,
                "download_url": download_url,
                "filename": filename,
                "timestamp": time.time()
            }
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save app cache: {e}")

    def _apply_cached_data(self, data):
        logger.info(f"New EmuMan Available (Cached): {data.get('version')}")
        self.latest_version = data.get("version")
        self.html_url = data.get("html_url")
        self.update_exe_url = data.get("download_url")
        self.update_exe_name = data.get("filename")

    def _delete_cache(self, cache_path):
        if os.path.exists(cache_path):
            try:
                os.remove(cache_path)
                logger.info("Stale cache file removed.")
            except Exception as e:
                logger.warning(f"Failed to remove stale cache: {e}")
