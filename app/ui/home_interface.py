import os
import sys
import json
import subprocess
from pathlib import Path

from app.utils.logger import get_logger
logger = get_logger(__name__)

from PySide6.QtCore import Qt, QFileSystemWatcher, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (DisplayLabel, setFont, FluentIcon as FIF, TransparentToolButton,
                            InfoBar, InfoBarPosition, ImageLabel, CaptionLabel, MessageBox,
                            MessageBoxBase, SubtitleLabel, ComboBox)

from app.config import LANG_MAP, CURRENT_VERSION
from app.core.version_manager import VersionManager
from app.core.asset_manager import AssetManager
from app.core.file_processor import FileProcessor
from app.core.cache_manager import CacheManager
from app.core.app_updater import AppUpdater
from app.core.firmware_manager import FirmwareManager
from app.ui.components.channel_card import ChannelCard
from app.utils.path_utils import get_resource_path, open_directory

class DownloadSelectionDialog(MessageBoxBase):
    def __init__(self, parent, title, items, best_index=0):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title, self)
        self.viewLayout.addWidget(self.titleLabel)
        
        select_text = parent.lang.get("select_download", "Select download:") if hasattr(parent, 'lang') else "Select download:"
        
        self.contentLabel = CaptionLabel(select_text, self)
        self.viewLayout.addWidget(self.contentLabel)

        self.comboBox = ComboBox(self)
        for name, url in items:
            self.comboBox.addItem(name, userData=url)
        
        self.comboBox.setCurrentIndex(best_index)
        self.viewLayout.addWidget(self.comboBox)
        self.widget.setMinimumWidth(400)

    def get_selected(self):
        return self.comboBox.currentText(), self.comboBox.currentData()


class HomeInterface(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName('homeInterface')
        self.syncInfoBar = None
        
        # State & Services
        self.m_versions = []
        self.n_versions = []
        self.downloading_versions = set()
        self.cloud_changelogs = {}
        self.cloud_assets = {}
        self.current_download_params = {}
        self.lang = LANG_MAP.get("en")
        
        # Selection Restore State
        self.base_config = {}
        if os.path.exists("config.json"):
            try:
                with open("config.json", 'r', encoding='utf-8') as f:
                    self.base_config = json.load(f)
            except: pass
            
        self.restore_master = None
        self.restore_nightly = None
        if self.base_config.get("remember_last_selection", True):
            self.restore_master = self.base_config.get("last_master_version")
            self.restore_nightly = self.base_config.get("last_nightly_version")
        
        self.version_mgr = VersionManager()
        self.asset_mgr = AssetManager()
        self.file_processor = FileProcessor()
        # Connect FileProcessor signals
        self.file_processor.download_progress.connect(self.on_download_progress)
        self.file_processor.process_finished.connect(self.on_process_finished)
        self.file_processor.manual_required.connect(self.on_manual_required)
        self.file_processor.process_cancelled.connect(self.on_process_cancelled)
        
        self.cache_manager = CacheManager()
        self.cache_manager.sync_started.connect(self.on_sync_started)
        self.cache_manager.sync_finished.connect(self.on_sync_finished)
        self.cache_manager.sync_error.connect(self.on_sync_error)
        
        self.app_updater = AppUpdater()
        
        # UI
        self.initLayout()
        
        # Logic init
        # Bind AppUpdater UI refs
        self.app_updater.bind_ui(self.updateBadge, self.updateLabel, self.subTitle, self.window(), self.lang)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.refresh_local_and_ui)
        self.last_scan_counts = (-1, -1)
        
        # Optimized Init Flow
        init_lang = "en"
        if os.path.exists("config.json"):
            try:
                with open("config.json", 'r', encoding='utf-8') as f:
                    init_lang = json.load(f).get("lang", "en")
            except Exception: pass
            
        self.refresh_language(init_lang, initial=True)
        self.update_watcher_path()
        self.load_initial_cache()
        QTimer.singleShot(100, self.check_app_update)

    def initLayout(self):
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(30, 20, 30, 30)
        self.v_layout.setSpacing(20)

        # Header
        header = QHBoxLayout()
        logo = ImageLabel(get_resource_path('resources/logo.png'), self)
        logo.setFixedSize(48, 48)
        
        titles = QVBoxLayout()
        titles.setSpacing(4)
        
        titleRow = QHBoxLayout()
        self.mainTitle = DisplayLabel("EmuMan", self)
        self.mainTitle.setObjectName("mainTitle")
        setFont(self.mainTitle, 28)
        self.updateBadge = TransparentToolButton(FIF.CLOUD_DOWNLOAD, self)
        self.updateBadge.hide()
        self.updateBadge.clicked.connect(self.start_self_update)
        titleRow.addWidget(self.mainTitle)
        titleRow.addWidget(self.updateBadge, 0, Qt.AlignTop)
        titleRow.addStretch(1)
        
        subRow = QHBoxLayout()
        self.subTitle = CaptionLabel(f"Eden Emulator Manager | {CURRENT_VERSION}", self)
        self.updateLabel = CaptionLabel("", self)
        self.updateLabel.hide()
        self.updateLabel.setStyleSheet("CaptionLabel { color: #ff4757; font-weight: bold; }")
        subRow.addWidget(self.subTitle)
        subRow.addWidget(self.updateLabel)
        subRow.addStretch(1)
        
        titles.addLayout(titleRow)
        titles.addLayout(subRow)

        self.openUserFolderBtn = TransparentToolButton(FIF.FOLDER, self)
        self.openUserFolderBtn.setToolTip(self.lang.get("open_user_folder", "Open Data Folder"))
        self.openUserFolderBtn.clicked.connect(self.open_user_data_folder)
        
        self.refreshBtn = TransparentToolButton(FIF.SYNC, self)
        self.refreshBtn.setToolTip(self.lang.get("refresh_data", "Refresh"))
        self.refreshBtn.clicked.connect(self.start_data_sync)
        
        self.openEdenFolderBtn = TransparentToolButton(FIF.GAME, self)
        self.openEdenFolderBtn.setToolTip(self.lang.get("open_eden_folder", "Open Eden Folder"))
        self.openEdenFolderBtn.clicked.connect(self.open_eden_folder)
        
        header.addWidget(logo)
        header.addSpacing(15)
        header.addLayout(titles)
        header.addStretch(1)
        header.addWidget(self.openEdenFolderBtn)
        header.addWidget(self.openUserFolderBtn)
        header.addWidget(self.refreshBtn)
        self.v_layout.addLayout(header)

        # Cards
        self.dashboard = QHBoxLayout()
        self.dashboard.setSpacing(25)
        
        self.masterCard = ChannelCard("master", self)
        self.nightlyCard = ChannelCard("nightly", self)
        
        for card in [self.masterCard, self.nightlyCard]:
            card.launch_requested.connect(self.on_launch_clicked)
            card.download_requested.connect(self.on_download_clicked)
            card.selection_changed.connect(self.on_selection_changed)
            self.dashboard.addWidget(card, 1)
            
        self.v_layout.addLayout(self.dashboard, 1)

    def refresh_language(self, lang_code, initial=False):
        if initial:
            logger.info(f"Loaded initial language: {lang_code}")
        else:
            logger.info(f"User changed language to: {lang_code}")
        self.lang = LANG_MAP.get(lang_code, LANG_MAP["en"])
        self.app_updater.lang = self.lang
        self.masterCard.refresh_language(self.lang)
        self.nightlyCard.refresh_language(self.lang)
        self.on_selection_changed("master")
        self.on_selection_changed("nightly")

        
        self.refreshBtn.setToolTip(self.lang.get("refresh_data", "Refresh"))
        self.openUserFolderBtn.setToolTip(self.lang.get("open_user_folder", "Open Data Folder"))
        self.openEdenFolderBtn.setToolTip(self.lang.get("open_eden_folder", "Open Eden Folder"))
        
    def load_initial_cache(self):
        # Use our persistent manager instance
        is_fresh, data = self.cache_manager.is_cache_fresh()
        
        # 1. Always load existing data if available (even if stale) to populate UI immediately
        if data:
            logger.info(f"Local API cache loaded. Fresh: {is_fresh}")
            self.on_sync_finished(data, silent=True)
            
        # 2. If missing or expired, trigger background sync
        if not is_fresh:
            logger.info("Cache missing or expired. Starting data sync...")
            self.cache_manager.start_sync_task(force=False)

    def refresh_local_and_ui(self):
        base_path = ""
        if os.path.exists("config.json"): 
            try:
                with open("config.json", 'r', encoding='utf-8') as f:
                    base_path = json.load(f).get("path", "")
            except: pass
        
        # Default path fallback
        if not base_path:
            base_path = os.path.join(os.getcwd(), "downloads", "eden")
            # Create default directory if it doesn't exist (optional here, but good for scanning)
            if not os.path.exists(base_path):
                 try: os.makedirs(base_path, exist_ok=True)
                 except: pass

        m_local = self.version_mgr.get_local_list("master", base_path, self.m_versions)
        n_local = self.version_mgr.get_local_list("nightly", base_path, self.n_versions)
        
        # Only log scan results if we have cloud version data to match against
        if self.m_versions or self.n_versions:
            if (len(m_local), len(n_local)) != self.last_scan_counts:
                logger.info(f"Local Scan: Found {len(m_local)} Master, {len(n_local)} Nightly versions.")
                self.last_scan_counts = (len(m_local), len(n_local))
        
        m_all = list(set(self.m_versions) | set(m_local.keys()))
        m_full_list = self.version_mgr.sort_versions(m_all)
        
        n_all = list(set(self.n_versions) | set(n_local.keys()))
        n_full_list = sorted(n_all, key=lambda x: self.version_mgr.get_short_version(x), reverse=True)

        self.masterCard.update_data(m_full_list, m_local, self.downloading_versions)
        self.nightlyCard.update_data(n_full_list, n_local, self.downloading_versions)

        # Restore selection if pending (One-time)
        if self.restore_master:
            idx = self.masterCard.combo.findData(self.restore_master)
            if idx >= 0: self.masterCard.combo.setCurrentIndex(idx)
            self.restore_master = None

        if self.restore_nightly:
            idx = self.nightlyCard.combo.findData(self.restore_nightly)
            if idx >= 0: self.nightlyCard.combo.setCurrentIndex(idx)
            self.restore_nightly = None

    def on_selection_changed(self, branch):
        card = self.masterCard if branch == "master" else self.nightlyCard
        tag = card.combo.currentData()
        if not tag: return
        
        # Update Changelog
        content = self.cloud_changelogs.get(branch, {}).get(tag)
        if not content:
            cache_path = os.path.join("changelogs", f"{branch}_{tag}.md")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f: content = f.read()
                except Exception: pass
        
        card.set_changelog(content or self.lang.get("changelog_placeholder", "### Loading..."))
        card.update_ui_state()

    def start_data_sync(self):
        self.refreshBtn.setEnabled(False)
        self.cache_manager.start_sync_task(force=True)

    def on_sync_started(self):
        self.syncInfoBar = InfoBar.info(title=self.lang.get("sync_data", "Syncing..."), content="", parent=self, duration=-1)

    def on_sync_error(self):
        self.refreshBtn.setEnabled(True)
        if self.syncInfoBar: self.syncInfoBar.close(); self.syncInfoBar = None
        InfoBar.warning(title=self.lang.get("network_error", "Error"), content="", parent=self, duration=3000)

    def on_sync_finished(self, data, silent=False):
        self.refreshBtn.setEnabled(True)
        if self.syncInfoBar: self.syncInfoBar.close(); self.syncInfoBar = None
        
        changed = (data.get("versions", {}).get("master", []) != self.m_versions)
        self.m_versions = data.get("versions", {}).get("master", [])
        self.n_versions = data.get("versions", {}).get("nightly", [])
        self.cloud_changelogs = data.get("changelogs", {})
        self.cloud_assets = data.get("assets", {})
        
        self.refresh_local_and_ui()
        
        # Trigger changelog display for both cards
        self.on_selection_changed("master")
        self.on_selection_changed("nightly")
        
        if not silent:
            msg = self.lang.get("sync_data_success" if changed else "sync_data_latest", "Done")
            InfoBar.success(title=msg, content="", parent=self, duration=2000)

    def open_user_data_folder(self):
        """Open the Eden user data folder (nand, keys, etc)."""
        eden_exe_path = self._get_current_eden_exe()
        data_path = FirmwareManager.get_user_data_path(eden_exe_path)
        
        # Ensure path is absolute for safety
        if data_path:
            data_path = Path(data_path).resolve()
        
        if data_path and data_path.exists():
            success, msg = open_directory(str(data_path))
            if not success:
                 InfoBar.error(title=self.lang.get("error", "Error"), content=msg, parent=self)
        else:
            # Try to create it if system default
            if not eden_exe_path and data_path: 
                 # System default assumption
                 try:
                     data_path.mkdir(parents=True, exist_ok=True)
                     success, msg = open_directory(str(data_path))
                     if not success:
                         InfoBar.error(title=self.lang.get("error", "Error"), content=msg, parent=self)
                     return
                 except: pass
            
            InfoBar.warning(
                title=self.lang.get("user_folder_not_found", "Folder Not Found"),
                content=f"Path: {data_path}",
                parent=self,
                duration=3000
            )

    def open_eden_folder(self):
        """Open the configured Eden Emulator Download Folder"""
        base_path = ""
        if os.path.exists("config.json"):
            try:
                with open("config.json", 'r', encoding='utf-8') as f:
                    base_path = json.load(f).get("path", "")
            except Exception: pass
        
        # Fallback to default if not configured
        if not base_path:
            base_path = os.path.join(os.getcwd(), "downloads", "eden")
            
        if base_path:
            # Create if missing (user expectation: "Open MY folder")
            if not os.path.exists(base_path):
                try: os.makedirs(base_path, exist_ok=True)
                except: pass
                
            if os.path.exists(base_path):
                success, msg = open_directory(base_path)
                if not success:
                    InfoBar.error(title=self.lang.get("error", "Error"), content=msg, parent=self)
                return
        
        # Fallback error (Should technically be unreachable if creation works)
        InfoBar.warning(
            title=self.lang.get("file_not_found", "File Not Found"),
            content="Eden Emulator path invalid.",
            parent=self
        ) 


    def on_selection_changed(self, branch):
        card = self.masterCard if branch == "master" else self.nightlyCard
        tag = card.combo.currentData()
        if not tag: return
        
        # Update Changelog
        content = self.cloud_changelogs.get(branch, {}).get(tag)
        if not content:
            cache_path = os.path.join("changelogs", f"{branch}_{tag}.md")
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f: content = f.read()
                except Exception: pass
        
        card.set_changelog(content or self.lang.get("changelog_placeholder", "### Loading..."))
        card.update_ui_state()

    def on_launch_clicked(self, branch):
        card = self.masterCard if branch == "master" else self.nightlyCard
        tag = card.combo.currentData()
        with open("config.json", 'r', encoding='utf-8') as f:
            base = json.load(f).get("path", "")
        
        known_tags = self.m_versions if branch == "master" else self.n_versions
        local_map = self.version_mgr.get_local_list(branch, base, known_tags)
        exe = self.version_mgr.find_executable(base, local_map.get(tag, ""))
        
        if exe and os.path.exists(exe):
            self.file_processor.fix_executable_permission(exe)
            logger.info(f"Launching: {exe}")
            subprocess.Popen(exe, cwd=os.path.dirname(exe), shell=(sys.platform != "win32"))
        else:
            InfoBar.error(self.lang.get("error", "Error"), self.lang.get("exe_not_found", "Executable not found: {}").format(exe), parent=self)

    def on_download_clicked(self, branch):
        card = self.masterCard if branch == "master" else self.nightlyCard
        tag = card.combo.currentData()
        self.current_download_params = {"branch": branch, "tag": tag}
        
        # Asset Selection Logic
        assets = self.cloud_assets.get(tag, [])
        valid = [a for a in assets if self.asset_mgr.is_file_for_platform(a["name"])]
        if not valid:
            InfoBar.warning(self.lang.get("no_build", "No Build"), self.lang.get("no_platform_build", "No compatible build found."), parent=self)
            return

        # Preference Score
        with open("config.json", 'r', encoding='utf-8') as f: base = json.load(f).get("path", "")
        local_map = self.version_mgr.get_local_list(branch, base, [])
        pref_features = [f for f in ["msvc", "clang", "mingw", "appimage", "deb"] if any(f in v.lower() for v in local_map.values())]
        valid.sort(key=lambda x: self.asset_mgr.calculate_score(x["name"], pref_features), reverse=True)
        
        items = [(a["name"], a["browser_download_url"]) for a in valid]
        dialog = DownloadSelectionDialog(self, f"Download {tag}", items)
        if dialog.exec():
            fname, url = dialog.get_selected()
            if fname.lower().endswith(".7z"):
                title = self.lang.get("extract_manual", "Manual required")
                msg = f"{self.lang.get('extract_manual_msg', '')}\n\n{fname}\n\nContinue?"
                if not MessageBox(title, msg, self.window()).exec(): return
            
            self.start_download(url, fname, branch, tag)

    def start_download(self, url, filename, branch, tag):
        base = ""
        if os.path.exists("config.json"):
            try:
                with open("config.json", 'r', encoding='utf-8') as f: base = json.load(f).get("path", "")
            except: pass
        
        # Default path fallback
        if not base:
            base = os.path.join(os.getcwd(), "downloads", "eden")
            
        # Ensure directory exists
        if not os.path.exists(base):
            try:
                os.makedirs(base, exist_ok=True)
                logger.info(f"Created default download directory: {base}")
            except Exception as e:
                InfoBar.error(
                    title=self.lang.get("error", "Error"),
                    content=self.lang.get("create_dir_fail", "Failed to create directory: {}\n{}").format(base, e),
                    parent=self,
                    duration=4000
                )
                return

        self.downloading_versions.add(tag)
        self.current_download_tag = tag
        self.current_download_branch = branch
        self.refresh_local_and_ui()
        
        # Create persistent InfoBar for cancellation
        self.download_active = True
        self.downloadInfoBar = InfoBar.info(
            title=self.lang.get("downloading", "Downloading..."),
            content=f"0% - 0.0 MB/s",
            parent=self,
            duration=-1 
        )
        self.downloadInfoBar.destroyed.connect(self.on_download_info_closed)
        
        save_path = os.path.join(base, filename)
        
        # Show progress bar on the correct card
        card = self.masterCard if branch == "master" else self.nightlyCard
        card.set_download_progress(0)
        
        # Delegate background task to FileProcessor
        self.file_processor.start_download_task(url, save_path, branch, tag)

    def on_download_progress(self, progress, speed=""):
        """Generic handler for download progress, updating both cards if active."""
        if hasattr(self, 'downloadInfoBar') and self.downloadInfoBar:
             if hasattr(self.downloadInfoBar, 'contentLabel'):
                 content = f"{progress}%"
                 if speed:
                     content += f" - {speed}"
                 self.downloadInfoBar.contentLabel.setText(content)
        
        if getattr(self, 'current_download_tag', None):
             pass

        branch = getattr(self, 'current_download_branch', None)
        if branch:
            card = self.masterCard if branch == "master" else self.nightlyCard
            card.set_download_progress(progress)

    def on_process_finished(self, ok, result_msg, branch, tag):
        # result_msg is final path if success, or error msg if failed
        self.download_active = False
        if hasattr(self, 'downloadInfoBar') and self.downloadInfoBar:
            self.downloadInfoBar.close()
            self.downloadInfoBar = None

        card = self.masterCard if branch == "master" else self.nightlyCard
        # Reset card progress state
        card.set_download_progress(-1)
        
        if tag in self.downloading_versions: self.downloading_versions.remove(tag)
        
        if ok:
            if not result_msg.lower().endswith(".7z"):
                InfoBar.success(self.lang.get("done", "Done"), self.lang.get("download_success", "Ready"), parent=self)
            self.refresh_local_and_ui()
        else:
            self.refresh_local_and_ui()
            # Avoid dual language "Download failed" / "下载失败"
            content = result_msg
            if content == "Download failed":
                content = self.lang.get("network_error", "Check network connection")
            
            InfoBar.error(self.lang.get("download_failed", "Failed"), content, parent=self)

    def save_selection_state(self):
        """Save current selection to config if enabled."""
        config_path = "config.json"
        
        try:
            cfg = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
            
            if cfg.get("remember_last_selection", True):
                cfg["last_master_version"] = self.masterCard.combo.currentData()
                cfg["last_nightly_version"] = self.nightlyCard.combo.currentData()
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(cfg, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save selection state: {e}")

    def on_download_info_closed(self):
        """Handle user closing the download InfoBar -> Cancel download."""
        # InfoBar is already destroyed/destroying, clear reference immediately
        self.downloadInfoBar = None
        
        if getattr(self, 'download_active', False):
            logger.info("User requested download cancellation.")
            self.download_active = False
            self.file_processor.cancel_download_task()

    def on_process_cancelled(self):
        """Handle successful cancellation signal from FileProcessor."""
        self.download_active = False
        
        if hasattr(self, 'downloadInfoBar') and self.downloadInfoBar:
            try:
                self.downloadInfoBar.close()
            except RuntimeError: pass
            self.downloadInfoBar = None

        InfoBar.info(
            title=self.lang.get("download_cancelled", "Download Cancelled"), 
            content="", 
            parent=self, 
            duration=2000
        )
        
        # Reset state
        if hasattr(self, 'current_download_tag') and self.current_download_tag:
             if self.current_download_tag in self.downloading_versions:
                 self.downloading_versions.remove(self.current_download_tag)
             self.current_download_tag = None
        
        # Reset UI on active card if possible
        branch = getattr(self, 'current_download_branch', None)
        if branch:
            card = self.masterCard if branch == "master" else self.nightlyCard
            card.set_download_progress(-1)
            self.current_download_branch = None
             
        self.refresh_local_and_ui()

    def on_manual_required(self, path):
         InfoBar.warning(title=self.lang.get("extract_manual"), content=f"{self.lang.get('extract_manual_msg')} {path}", parent=self, duration=5000)

    def update_watcher_path(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json", 'r', encoding='utf-8') as f:
                    path = json.load(f).get("path", "")
                if path and os.path.exists(path):
                    current_watched = self.watcher.directories()
                    if path not in current_watched:
                        if current_watched: self.watcher.removePaths(current_watched)
                        self.watcher.addPath(path)
                        logger.info(f"Watcher updated to: {path}")
            except Exception: pass

    def check_app_update(self):
        """Invoke modular app update check (async)."""
        # Check config first
        if os.path.exists("config.json"):
            try:
                with open("config.json", 'r', encoding='utf-8') as f:
                    if not json.load(f).get("check_update_at_start", True):
                        logger.info("Startup update check skipped by user config.")
                        return
            except Exception: pass
            
        self.app_updater.start_check_update_async()

    def start_self_update(self):
        """Invoke modular self-update workflow."""
        self.app_updater.start_self_update()

    def scan_local_versions(self):
        """Compatibility alias for the new refresh_local_and_ui method."""
        self.refresh_local_and_ui()

    def update_status(self):
        """Compatibility alias to refresh UI labels and states."""
        self.on_selection_changed("master")
        self.on_selection_changed("nightly")

    def _get_current_eden_exe(self):
        """获取当前选中的 Eden 可执行文件路径"""
        if not os.path.exists("config.json"):
            return None
        
        with open("config.json", 'r', encoding='utf-8') as f:
            base_path = json.load(f).get("path", "")
        
        if not base_path:
            return None
        
        master_tag = self.masterCard.combo.currentData()
        if master_tag:
            local_map = self.version_mgr.get_local_list("master", base_path, self.m_versions)
            exe = self.version_mgr.find_executable(base_path, local_map.get(master_tag, ""))
            if exe and os.path.exists(exe):
                return exe
        
        nightly_tag = self.nightlyCard.combo.currentData()
        if nightly_tag:
            local_map = self.version_mgr.get_local_list("nightly", base_path, self.n_versions)
            exe = self.version_mgr.find_executable(base_path, local_map.get(nightly_tag, ""))
            if exe and os.path.exists(exe):
                return exe
        
        return None
    



