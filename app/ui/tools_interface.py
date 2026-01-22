import os
import time
import sys
import json
import re
import zipfile
from pathlib import Path

from app.utils.logger import get_logger
logger = get_logger(__name__)

from PySide6.QtCore import Qt, Signal, QUrl, QThread, QTimer
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, 
                               QScrollArea, QTableWidgetItem, QHeaderView, QTreeWidget,
                               QTreeWidgetItem, QSizePolicy, QFileDialog)
from qfluentwidgets import (CardWidget, StrongBodyLabel, BodyLabel, PrimaryPushButton, 
                            PushButton, FluentIcon as FIF, IconWidget, MessageBox, 
                            MessageBoxBase, SubtitleLabel, InfoBar, TransparentToolButton,
                            TableWidget, RoundMenu, Action, setFont)

from app.config import LANG_MAP
from app.core.backup_manager import BackupManager
from app.core.keys_manager import KeysManager
from app.core.mod_manager import ModManager
from app.core.firmware_manager import FirmwareManager, FirmwareInstallWorker, FirmwareUpdateCheckWorker


class RestoreDialog(MessageBoxBase):
    """Dialog to list and restore backups."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = parent.lang if hasattr(parent, 'lang') else LANG_MAP["en"]
        self.titleLabel = SubtitleLabel(self.lang.get("save_restore", "Restore Saves"), self)
        
        self.viewLayout.addWidget(self.titleLabel)
        
        # Table
        self.table = TableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([
            self.lang.get("col_date", "Date"), 
            self.lang.get("col_name", "Name"), 
            self.lang.get("col_size", "Size")
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(TableWidget.SelectRows)
        self.table.setSelectionMode(TableWidget.SingleSelection)
        self.table.setMinimumHeight(300)
        self.table.setMinimumWidth(550)
         
        self.table.setBorderVisible(True)
        self.table.setBorderRadius(8)
        self.table.setWordWrap(False)
        
        self.viewLayout.addWidget(self.table)

        # Function Row (Delete)
        self.funcLayout = QHBoxLayout()
        self.deleteBtn = PushButton(self.lang.get("delete", "Delete"), self, FIF.DELETE)
        self.deleteBtn.clicked.connect(self.prompt_delete)
        
        self.funcLayout.addStretch(1)
        self.funcLayout.addWidget(self.deleteBtn)
        self.viewLayout.addLayout(self.funcLayout)
        
        self.refresh_list()
        
        # Context Menu
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        
        # We override standard buttons
        self.yesButton.setText(self.lang.get("save_restore", "Restore"))
        self.cancelButton.setText(self.lang.get("cancel", "Cancel"))
        
        self.widget.setMinimumWidth(600)

    def refresh_list(self):
        backups = BackupManager.get_backup_list()
        self.table.setRowCount(len(backups))
        
        for i, b in enumerate(backups):
            date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(b['time']))
            
            self.table.setItem(i, 0, QTableWidgetItem(date_str))
            self.table.setItem(i, 1, QTableWidgetItem(b['name']))
            self.table.setItem(i, 2, QTableWidgetItem(b['size_str']))
            
            # Store full path in user data of first item
            self.table.item(i, 0).setData(Qt.UserRole, str(b['path']))

    def get_selected_path(self):
        row = self.table.currentRow()
        if row >= 0:
            return self.table.item(row, 0).data(Qt.UserRole)
        return None

    def show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item: return
        
        menu = RoundMenu(parent=self)
        delete_action = Action(FIF.DELETE, self.lang.get("delete", "Delete"), self)
        delete_action.triggered.connect(self.prompt_delete)
        menu.addAction(delete_action)
        menu.exec(self.table.mapToGlobal(pos))

    def prompt_delete(self):
        path = self.get_selected_path()
        if not path: return
        
        w = MessageBox(
            self.lang.get("delete_confirm_title", "Confirm Delete"),
            self.lang.get("delete_confirm", "Delete this backup?"),
            self.window()
        )
        if w.exec():
            self.delete_selected()

    def delete_selected(self):
        path = self.get_selected_path()
        if path:
             if BackupManager.delete_backup(path):
                 self.refresh_list()

class ModManagerDialog(MessageBoxBase):
    """Dialog to list and toggle mods."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = parent.lang if hasattr(parent, 'lang') else LANG_MAP["en"]
        self.titleLabel = SubtitleLabel(self.lang.get("mod_manager", "Mod Manager"), self)
        self.viewLayout.addWidget(self.titleLabel)
        
        # Tree
        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Title ID / Mod Name", "Status"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.setMinimumHeight(350)
        self.tree.setMinimumWidth(600)
        self.tree.setAlternatingRowColors(True)
        
        self.viewLayout.addWidget(self.tree)
        
        # Actions
        self.funcLayout = QHBoxLayout()
        self.toggleBtn = PushButton(self.lang.get("toggle_mod", "Toggle"), self, FIF.EDIT)
        self.toggleBtn.clicked.connect(self.toggle_selected)
        
        self.openBtn = PushButton(self.lang.get("open_mod_folder", "Open Folder"), self, FIF.FOLDER)
        self.openBtn.clicked.connect(self.open_folder)
        
        self.funcLayout.addWidget(self.toggleBtn)
        self.funcLayout.addWidget(self.openBtn)
        self.funcLayout.addStretch(1)
        self.viewLayout.addLayout(self.funcLayout)
        
        self.refresh_list()
        
        # Context Menu
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
        self.yesButton.hide() # We don't need a primary action button, just Close
        self.cancelButton.setText(self.lang.get("close", "Close")) 

    def get_eden_exe(self):
        # Helper to traverse up parents to find ToolsInterface and ask it
        # Or just use the one passed to parent? ToolsInterface._get_eden_exe is a bit weak right now.
        # Let's rely on ModManager defaults or improve ToolsInterface later.
        if hasattr(self.parent(), '_get_eden_exe'):
            return self.parent()._get_eden_exe()
        return None

    def refresh_list(self):
        self.tree.clear()
        mods = ModManager.list_mods(self.get_eden_exe())
        
        if not mods:
            item = QTreeWidgetItem([self.lang.get("no_mods_found", "No Mods Found"), ""])
            self.tree.addTopLevelItem(item)
            self.tree.setEnabled(False)
            return
            
        self.tree.setEnabled(True)
        for title_id, mod_list in mods.items():
            title_item = QTreeWidgetItem([title_id, f"({len(mod_list)})"])
            title_item.setExpanded(True)
            self.tree.addTopLevelItem(title_item)
            
            for mod in mod_list:
                status = self.lang.get("mod_enabled") if mod['enabled'] else self.lang.get("mod_disabled")
                mod_item = QTreeWidgetItem([mod['name'], status])
                # Store full path
                mod_item.setData(0, Qt.UserRole, str(mod['path']))
                
                # Visual cue for disabled
                if not mod['enabled']:
                     mod_item.setForeground(0, QColor("#808080"))
                     mod_item.setForeground(1, QColor("#808080"))
                else:
                     mod_item.setForeground(0, QColor("#2ecc71"))
                
                title_item.addChild(mod_item)

    def get_selected_mod_path(self):
        item = self.tree.currentItem()
        if item and item.parent(): # Ensure it's a mod not a TitleID
            return item.data(0, Qt.UserRole), item
        return None, None

    def toggle_selected(self):
        path, item = self.get_selected_mod_path()
        if path:
            # Check current status from text/color or re-derive?
            # Creating a unified toggle logic in Manager is safer
            is_enabled = "enabled" in item.text(1) or (item.foreground(0).color().name() == "#2ecc71")
            
            # If visual cue is unreliable, rely on filename logic in Manager.
            # But here we need to know what we are asking for.
            # ModManager.toggle_mod takes "enable" boolean? No.
            # Let's check ModManager.toggle_mod implementation.
            # It enables if disabled, and vice versa?
            # Wait, my implementation `toggle_mod(mod_path_str, enable)` takes explicit target state.
            
            # Simple toggle logic:
            currently_enabled = not str(path).endswith(".disabled")
            target_state = not currently_enabled
            
            success, res = ModManager.toggle_mod(path, target_state)
            if success:
                self.refresh_list()
            else:
                 InfoBar.error(self.lang.get("error", "Error"), res, parent=self)

    def open_folder(self):
        ModManager.open_mod_folder(self.get_eden_exe())
        if path := ModManager.get_load_dir(self.get_eden_exe()):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item or not item.parent(): return
        
        menu = RoundMenu(parent=self)
        toggle_action = Action(FIF.EDIT, self.lang.get("toggle_mod", "Toggle"), self)
        toggle_action.triggered.connect(self.toggle_selected)
        menu.addAction(toggle_action)
        menu.exec(self.tree.mapToGlobal(pos))

class FirmwareManagerDialog(MessageBoxBase):
    """Dialog to list and install local firmware."""
    """Dialog to list and install local firmware."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lang = parent.lang if hasattr(parent, 'lang') else LANG_MAP["en"]
        self.titleLabel = SubtitleLabel(self.lang.get("firmware_install_title", "Install Firmware"), self)
        self.viewLayout.addWidget(self.titleLabel)
        
        # Table
        self.table = TableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels([
            self.lang.get("col_version", "Version"), 
            self.lang.get("col_status", "Status"),
            self.lang.get("col_size", "Size")
        ])
        
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(TableWidget.SelectRows)
        self.table.setSelectionMode(TableWidget.SingleSelection)
        self.table.setMinimumHeight(300)
        self.table.setMinimumWidth(600)
        self.table.setAlternatingRowColors(True)
        
        self.viewLayout.addWidget(self.table)
        
        self.refresh_list()
        
        # Dialog buttons (Side by Side)
        self.yesButton.setText(self.lang.get("firmware_install_local", "Install"))
        self.yesButton.setIcon(FIF.DOWNLOAD)
        self.yesButton.clicked.disconnect()
        self.yesButton.clicked.connect(self.install_selected)
        
        self.cancelButton.setText(self.lang.get("cancel", "Cancel"))

    def get_eden_exe(self):
        if hasattr(self.parent(), '_get_eden_exe'):
            return self.parent()._get_eden_exe()
        return None

    def refresh_list(self):
        self.table.setRowCount(0)
        fw_list = FirmwareManager.list_local_firmware()
        
        # Check cache for remote version (non-blocking)
        remote_info = None
        try:
             cache_path = Path("cache") / "firmware_cache.json"
             if cache_path.exists():
                 with open(cache_path, 'r') as f:
                     data = json.load(f)
                     if data.get("version"):
                         remote_info = data
        except: pass

        # Combine lists? Or just append remote if not in local?
        # Note: Remote item needs special handling in install
        
        total_rows = len(fw_list)
        if remote_info:
             # Check if remote version is already local
             is_local = any(f['version'] == remote_info['version'] for f in fw_list)
             if not is_local:
                 total_rows += 1
        
        if total_rows == 0:
            self.table.setRowCount(1)
            self.table.setItem(0, 0, QTableWidgetItem(self.lang.get("firmware_no_local", "No local firmware")))
            self.table.item(0, 0).setTextAlignment(Qt.AlignCenter)
            self.table.setSpan(0, 0, 1, 3)
            self.table.setEnabled(False)
            return

        self.table.setEnabled(True)
        self.table.setRowCount(total_rows)
        
        # Get currently installed version
        current_version = FirmwareManager.get_firmware_version(self.get_eden_exe())
        
        row_idx = 0
        
        # Add Remote Item First if available and unique
        if remote_info and not any(f['version'] == remote_info['version'] for f in fw_list):
            self.table.setItem(row_idx, 0, QTableWidgetItem(remote_info['version']))
            
            # Tag: Remote vs Installed
            tag_text = self.lang.get("tag_remote", "Remote")
            tag_color = "#009db2" # Teal
            
            if current_version and remote_info['version'] == current_version:
                 tag_text = self.lang.get("tag_installed", "Installed")
                 tag_color = "#9b59b6" # Purple
            
            lbl = BodyLabel(tag_text, self)
            lbl.setStyleSheet(f"color: white; background-color: {tag_color}; border-radius: 4px; padding: 2px 8px;")
            lbl.setAlignment(Qt.AlignCenter)

            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 2, 0, 2)
            layout.addWidget(lbl)
            self.table.setCellWidget(row_idx, 1, container)
            
            # Size Column
            size_val = remote_info.get("size", 0)
            size_str = self.lang.get("online", "Online")
            if size_val > 0:
                size_str = f"{size_val / 1024 / 1024:.2f} MB"
            
            self.table.setItem(row_idx, 2, QTableWidgetItem(size_str))
            
            self.table.item(row_idx, 0).setData(Qt.UserRole, remote_info['download_url']) # Store URL
            self.table.item(row_idx, 0).setData(Qt.UserRole + 1, "remote") # Store Type
            row_idx += 1

        for fw in fw_list:
            self.table.setItem(row_idx, 0, QTableWidgetItem(fw['version']))
            
            # Tag: Local vs Installed
            tag_text = self.lang.get("tag_local", "Local")
            tag_color = "#2ecc71" # Green
            
            if current_version and fw['version'] == current_version:
                 tag_text = self.lang.get("tag_installed", "Installed")
                 tag_color = "#9b59b6" # Purple
            
            lbl = BodyLabel(tag_text, self)
            lbl.setStyleSheet(f"color: white; background-color: {tag_color}; border-radius: 4px; padding: 2px 8px;")
            lbl.setAlignment(Qt.AlignCenter)
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(0, 2, 0, 2)
            layout.addWidget(lbl)
            self.table.setCellWidget(row_idx, 1, container)
            
            self.table.setItem(row_idx, 2, QTableWidgetItem(fw['size_str']))
            
            self.table.item(row_idx, 0).setData(Qt.UserRole, fw['path'])
            self.table.item(row_idx, 0).setData(Qt.UserRole + 1, "local")
            row_idx += 1

    def get_selected_item_data(self):
        row = self.table.currentRow()
        if row >= 0:
            item = self.table.item(row, 0)
            if item:
                path = item.data(Qt.UserRole)
                ftype = item.data(Qt.UserRole + 1)
                version = item.text()
                return path, ftype, version
        return None, None, None

    def install_selected(self):
        path, ftype, version = self.get_selected_item_data()
        if not path: return
        
        # Check if already installed
        # Use get_firmware_version to ensure we match the displayed version (Log vs Local)
        current_version = FirmwareManager.get_firmware_version(self.get_eden_exe())
        
        # Confirm install
        msg = ""
        if current_version and version == current_version:
             msg = self.lang.get("firmware_already_installed", "Version {} is already installed.\nReinstall?").format(version)
        else:
            if ftype == "remote":
                msg = self.lang.get("firmware_install_confirm", "Download & Install {}?").format(version)
            else:
                msg = self.lang.get("firmware_install_confirm_local", "Install {}?").format(version)
            
        w = MessageBox(
            self.lang.get("firmware_install_title", "Install Firmware"),
            msg,
            self.window()
        )
        if w.exec():
            # Start install with progress dialog
            self.start_install_process(path, ftype, version)

    def start_install_process(self, path, ftype, version):
        progress = MessageBoxBase(self.window())
        progress.titleLabel = SubtitleLabel(self.lang.get("firmware_installing"), progress)
        progress.viewLayout.addWidget(progress.titleLabel)
        progress.contentLabel = BodyLabel(self.lang.get("firmware_install_please_wait", "Please wait..."), progress)
        progress.viewLayout.addWidget(progress.contentLabel)
        progress.yesButton.hide()
        progress.cancelButton.hide()
        
        if ftype == "remote":
            # 1. Config Cancellation
            progress.cancelButton.setText(self.lang.get("cancel", "Cancel"))
            progress.cancelButton.show()
            try: progress.cancelButton.clicked.disconnect()
            except: pass
            
            def on_cancel():
                progress.cancelButton.setEnabled(False)
                progress.contentLabel.setText(self.lang.get("cancelling", "Cancelling..."))
                if self.worker_thread: self.worker_thread.cancel()
                    
            progress.cancelButton.clicked.connect(on_cancel)

            # 2. Init Worker
            self.worker_thread = FirmwareInstallWorker(path, self.get_eden_exe(), version)
            def update_progress(phase, c, t, s):
                if phase == 'verifying':
                    progress.titleLabel.setText(self.lang.get("firmware_verifying", "Verifying Integrity..."))
                    progress.contentLabel.setText(s)
                elif phase == 'install':
                    progress.titleLabel.setText(self.lang.get("firmware_installing", "Installing Firmware..."))
                    progress.contentLabel.setText(f"{c}/{t}")
                elif phase == 'download':
                    progress.titleLabel.setText(self.lang.get("firmware_downloading", "Downloading Firmware..."))
                    # If connecting or preparing, show status only
                    if c == 0 and s:
                        progress.contentLabel.setText(s)
                    else:
                        progress.contentLabel.setText(f"{c}/{t} {s}")

            self.worker_thread.progress.connect(update_progress)
        else:
            # Local Install
            self.worker_thread = LocalInstallThread(path, self.get_eden_exe())
            def update_local_progress(c, t):
                progress.titleLabel.setText(self.lang.get("firmware_installing", "Installing Firmware..."))
                progress.contentLabel.setText(f"{c}/{t}")
            self.worker_thread.progress.connect(update_local_progress)

        # 3. Common Start
        self.worker_thread.finished.connect(lambda s, m: self.on_install_finished(s, m, progress))
        self.worker_thread.start()
        
        progress.exec()

    def on_install_finished(self, success, msg, dialog):
        dialog.close()
        if success:
             # Ask for restart
             w = MessageBox(
                 self.lang.get("firmware_restart_title", "Restart Required"),
                 self.lang.get("firmware_restart_msg", "Firmware installed successfully.\n\nStart Eden now to verify installation?"),
                 self.window()
             )
             w.yesButton.setText(self.lang.get("start_eden", "Start Eden"))
             w.cancelButton.setText(self.lang.get("later", "Later"))
             
             if w.exec():
                 # Switch to Home
                 main_win = self.window()
                 # Search up for MainWindow
                 from app.ui.main_window import MainWindow
                 while main_win and not isinstance(main_win, MainWindow):
                     main_win = main_win.parent()
                 
                 if main_win:
                     # Switch to Home and show info
                     main_win.switchTo(main_win.homeInterface)
                     InfoBar.info(
                         title="Ready",
                         content=self.lang.get("please_launch_eden", "Please launch Eden to complete verification."),
                         parent=main_win.homeInterface,
                         duration=3000
                     )
             
             self.refresh_list()
        else:
             InfoBar.error(self.lang.get("firmware_install_failed"), msg, parent=self.window())




class LocalInstallThread(QThread):
    progress = Signal(int, int)
    finished = Signal(bool, str)
    
    def __init__(self, zip_path, exe_path):
        super().__init__()
        self.zip_path = zip_path
        self.exe_path = exe_path
        
    def run(self):
        success, msg, _ = FirmwareManager.install_firmware(
            self.zip_path, 
            self.exe_path,
            lambda c, t: self.progress.emit(c, t)
        )
        self.finished.emit(success, msg)


class ToolCard(CardWidget):
    """Generic Tile for Toolbox."""
    def __init__(self, icon, title, desc, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(20, 20, 20, 20)
        
        # Header Row (Icon + Title + Stretch + TopRightWidget)
        self.headerLayout = QHBoxLayout()
        
        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(40, 40)
        
        self.titleLabel = SubtitleLabel(title, self)
        setFont(self.titleLabel, 18)
        
        self.headerLayout.addWidget(self.iconWidget)
        self.headerLayout.addSpacing(12)
        self.headerLayout.addWidget(self.titleLabel)
        self.headerLayout.addStretch(1)
        
        self.v_layout.addLayout(self.headerLayout)
        self.v_layout.addSpacing(10)

        # Middle Content (Description + Status)
        self.descLabel = BodyLabel(desc, self)
        self.descLabel.setWordWrap(True)
        self.descLabel.setStyleSheet("color: #808080; margin-bottom: 5px;")
        self.v_layout.addWidget(self.descLabel)
        
        self.statusLabel = BodyLabel("", self)
        self.statusLabel.setStyleSheet("color: #606060; font-size: 13px;")
        self.v_layout.addWidget(self.statusLabel)
        
        self.v_layout.addStretch(1)
        
        # Action Area
        self.actionLayout = QHBoxLayout()
        self.v_layout.addLayout(self.actionLayout)

    def add_top_right_button(self, icon, tooltip, callback):
        btn = TransparentToolButton(icon, self)
        btn.setToolTip(tooltip)
        btn.clicked.connect(callback)
        self.headerLayout.addWidget(btn)

    def set_status(self, text):
        self.statusLabel.setText(text)

    def add_action_button(self, text, icon=None, callback=None, is_primary=False):
        btn = PrimaryPushButton(text, self, icon) if is_primary else PushButton(text, self, icon)
        if callback:
            btn.clicked.connect(callback)
        self.actionLayout.addWidget(btn)
        return btn


class ToolsInterface(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName('toolsInterface')
        self.lang = getattr(parent, 'lang', LANG_MAP['en']) if parent else LANG_MAP['en']

        # Setup Scroll Area
        self.scrollArea = QScrollArea(self)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        
        self.view = QWidget(self.scrollArea)
        self.view.setObjectName("view")
        self.view.setStyleSheet("#view { background-color: transparent; }")
        self.scrollArea.setWidget(self.view)
        
        # Grid Layout for Tiles
        self.gridLayout = QGridLayout(self.view)
        self.gridLayout.setContentsMargins(36, 36, 36, 36)
        self.gridLayout.setSpacing(24)
        self.gridLayout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.gridLayout.setColumnStretch(0, 1)
        self.gridLayout.setColumnStretch(1, 1)
        
        # Initialize
        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.addWidget(self.scrollArea)
        
        self.fw_check_worker = None
        self.init_cards()
        
    def init_cards(self):
        # Save Manager Card
        self.saveCard = ToolCard(
            FIF.SAVE, 
            self.lang.get("save_manager", "Save Manager"),
            self.lang.get("save_manager_desc", "Backup and restore your game saves safely."),
            self
        )
        # Top right action: Open Backup Folder
        self.saveCard.add_top_right_button(
            FIF.FOLDER,
            self.lang.get("open_backup_folder", "Open Folder"),
            self.open_backup_folder
        )
        
        # Update Status
        self.update_last_backup_status()
        
        # Actions
        self.saveCard.add_action_button(
            self.lang.get("save_backup", "Backup"), 
            FIF.ADD, 
            self.on_backup_clicked, 
            is_primary=True
        )
        self.saveCard.add_action_button(
            self.lang.get("save_restore", "Restore"), 
            FIF.HISTORY, 
            self.on_restore_clicked
        )
        
        # Keys Manager Card
        self.keysCard = ToolCard(
            FIF.VPN, 
            self.lang.get("keys_manager", "Keys Manager"),
            self.lang.get("keys_manager_desc", "Manage emulation keys."),
            self
        )
        self.keysCard.add_top_right_button(
            FIF.FOLDER,
            self.lang.get("open_keys_folder", "Open Folder"),
            self.open_keys_folder
        )
        self.update_keys_status()
        
        self.keysCard.add_action_button(
            self.lang.get("import_keys", "Import Keys"),
            FIF.ADD,
            self.on_import_keys,
            is_primary=True
        )
        self.keysCard.add_action_button(
            self.lang.get("auto_scan_keys", "Auto Scan"),
            FIF.SYNC,
            self.on_auto_scan_keys
        )
        
        # Mod Manager Card
        self.modCard = ToolCard(
            FIF.TILES,
            self.lang.get("mod_manager", "Mod Manager"),
            self.lang.get("mod_manager_desc", "Manage emulation mods."),
            self
        )
        self.modCard.add_action_button(
            self.lang.get("mod_manager", "Manage Mods"),
            FIF.EDIT,
            self.on_mod_manager_clicked,
            is_primary=True
        )
        self.modCard.add_top_right_button(
            FIF.FOLDER,
            self.lang.get("open_mod_folder", "Open Folder"),
            self.open_mod_folder
        )
        self.update_mod_status()

        # Firmware Manager Card
        self.firmwareCard = ToolCard(
            FIF.UPDATE,
            self.lang.get("firmware_manager", "Firmware Manager"),
            self.lang.get("firmware_manager_desc", "Manage firmware."),
            self
        )
        self.firmwareUpdateBtn = self.firmwareCard.add_action_button(
             self.lang.get("firmware_check_update", "Check Update"),
             FIF.SYNC,
             lambda: self.check_firmware_update(manual=True),
             is_primary=False
        )
        self.firmwareInstallBtn = self.firmwareCard.add_action_button(
             self.lang.get("firmware_install_title", "Install Firmware"), 
             FIF.EDIT,
             self.on_firmware_manager_clicked,
             is_primary=True
        )
        self.firmwareCard.add_top_right_button(
             FIF.FOLDER,
             self.lang.get("open_firmware_folder", "Open Folder"),
             self.open_firmware_folder
        )

        # Log Manager Card
        self.logCard = ToolCard(
            FIF.CODE,
            self.lang.get("log_manager", "Log Manager"),
            self.lang.get("log_manager_desc", "Manage application logs."),
            self
        )
        self.logCard.add_top_right_button(
            FIF.FOLDER,
            self.lang.get("open_log_dir", "Open Folder"),
            self.open_log_folder
        )
        self.logCard.add_action_button(
            self.lang.get("export_logs", "Export Logs"),
            FIF.SHARE,
            self.export_logs,
            is_primary=True
        )
        
        # Add Cards to Grid
        self.gridLayout.addWidget(self.saveCard, 0, 0)
        self.gridLayout.addWidget(self.firmwareCard, 0, 1)
        self.gridLayout.addWidget(self.keysCard, 1, 0)
        self.gridLayout.addWidget(self.modCard, 1, 1)
        self.gridLayout.addWidget(self.logCard, 2, 0)
        
        # Row Stretches
        self.gridLayout.setRowStretch(0, 0)
        self.gridLayout.setRowStretch(1, 0)
        self.gridLayout.setRowStretch(2, 1)

        # Initial check
        self.sync_installed_firmware_version()
        self.update_firmware_status()
        # Delay update check slightly
        QTimer.singleShot(1000, self.check_firmware_update)

    def update_mod_status(self):
        mods = ModManager.list_mods(self._get_eden_exe())
        count = sum(len(v) for v in mods.values())
        self.modCard.set_status(self.lang.get("mod_installed_count", "Installed Mods: {}").format(count))

    def on_mod_manager_clicked(self):
        ModManagerDialog(self).exec()

    def open_mod_folder(self):
        path = ModManager.get_load_dir(self._get_eden_exe())
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            InfoBar.warning(title=self.lang.get("not_found", "Not Found"), content=str(path), parent=self)

    def sync_installed_firmware_version(self):
        """Syncs installed firmware version from Eden log to cache."""
        try:
            eden_exe_path = self._get_eden_exe()
            log_path = None
            
            if eden_exe_path and os.path.exists(eden_exe_path):
               log_path = Path(eden_exe_path).parent / "logs" / "eden.log"

            # Fallback to system log path
            if not log_path or not log_path.exists():
                if sys.platform == "win32":
                    log_path = Path.home() / "AppData" / "Roaming" / "eden" / "logs" / "eden.log"
                else:
                    log_path = Path.home() / ".local" / "share" / "eden" / "logs" / "eden.log"
            
            if log_path and log_path.exists():
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    match = re.search(r"Firmware version: ([0-9.]+)", content)
                    if match:
                        version = match.group(1)
                        logger.info(f"Synced installed firmware version: {version}")
                        
                        cache_path = Path("cache") / "firmware_cache.json"
                        data = {}
                        if cache_path.exists():
                            try:
                                with open(cache_path, 'r') as f: data = json.load(f)
                            except: pass
                        
                        data["installed_version"] = version
                        cache_path.parent.mkdir(exist_ok=True)
                        with open(cache_path, 'w') as f: json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to sync installed firmware version: {e}")

    def update_firmware_status(self):
        """Update firmware card status text."""
        eden_exe_path = self._get_eden_exe()
        text, _ = FirmwareManager.get_display_text(eden_exe_path, self.lang)
        self.firmwareCard.set_status(text)

    def check_firmware_update(self, manual=False):
        """Check for firmware updates from GitHub."""
        if self.fw_check_worker and self.fw_check_worker.isRunning():
            if manual:
                 InfoBar.info(self.lang.get("sync_data", "Checking..."), "", parent=self)
            return

        self.firmwareCard.set_status(self.lang.get("sync_data", "Checking..."))
        self.firmwareUpdateBtn.setEnabled(False)
        self.is_manual_check = manual
        
        current_version, _ = FirmwareManager._load_local_firmware_record()
        self.fw_check_worker = FirmwareUpdateCheckWorker(current_version)
        self.fw_check_worker.finished.connect(self.on_firmware_check_finished)
        self.fw_check_worker.start()

    def on_firmware_check_finished(self, version, url):
        self.firmwareUpdateBtn.setEnabled(True)
        self.update_firmware_status() # Restore "Installed: ..." text
        
        if version:
             # Update available
             self.firmwareCard.set_status(self.lang.get("firmware_update_available", "Update Available: {}").format(version))
             self.firmwareUpdateBtn.setText(self.lang.get("firmware_install_local", "Update")) 
             try: self.firmwareUpdateBtn.clicked.disconnect() 
             except: pass
             self.firmwareUpdateBtn.clicked.connect(lambda: self.start_firmware_update(version, url))
        else:
             self.firmwareUpdateBtn.setText(self.lang.get("firmware_check_update", "Check Update"))
             # Restore handler
             try: self.firmwareUpdateBtn.clicked.disconnect() 
             except: pass
             self.firmwareUpdateBtn.clicked.connect(lambda: self.check_firmware_update(manual=True))
             
             if getattr(self, 'is_manual_check', False):
                 InfoBar.success(self.lang.get("sync_data_latest", "Up to date"), "", parent=self)
                 self.is_manual_check = False

    def start_firmware_update(self, version, url):
        """Start invalid firmware update flow."""
        title = self.lang.get("firmware_install_title", "Install Firmware")
        msg = self.lang.get("firmware_install_confirm", "Install firmware {}?").format(version)
        
        if MessageBox(title, msg, self.window()).exec():
             self.progressDialog = MessageBoxBase(self.window())
             self.progressDialog.titleLabel.setText(self.lang.get("firmware_installing", "Installing..."))
             self.progressMsg = SubtitleLabel("0%", self.progressDialog)
             self.progressDialog.viewLayout.addWidget(self.progressMsg)
             self.progressDialog.yesButton.hide()
             self.progressDialog.cancelButton.hide()
             self.progressDialog.show()
             
             self.downloader_thread = FirmwareDownloadInstallThread(url, version, self._get_eden_exe())
             self.downloader_thread.progress.connect(lambda phase, c, t, s: self.progressMsg.setText(f"{phase}: {c}/{t} {s}"))
             self.downloader_thread.finished.connect(self.on_firmware_update_finished)
             self.downloader_thread.start()

    def on_firmware_update_finished(self, success, msg):
        self.progressDialog.close()
        if success:
             InfoBar.success(self.lang.get("firmware_install_success", "Success"), msg, parent=self)
             self.sync_installed_firmware_version()
             self.update_firmware_status()
        else:
             InfoBar.error(self.lang.get("firmware_install_failed", "Failed"), msg, parent=self)

    def on_firmware_manager_clicked(self):
        FirmwareManagerDialog(self).exec()
        self.update_firmware_status()

    def open_firmware_folder(self):
        path = FirmwareManager.get_firmware_path_config()
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            # Create if not exists?
            try:
                os.makedirs(path, exist_ok=True)
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
            except:
                InfoBar.warning(title=self.lang.get("not_found", "Not Found"), content=str(path), parent=self)

    def update_last_backup_status(self):
        backups = BackupManager.get_backup_list()
        if backups:
            last = backups[0]
            date_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(last['time']))
            self.saveCard.set_status(self.lang.get("last_backup", "Last: {}").format(date_str))
        else:
            self.saveCard.set_status(self.lang.get("last_backup_none", "Last: Never"))

    def _get_eden_exe(self):
        """Get Eden executable path from config."""
        if os.path.exists("config.json"):
            try:
                with open("config.json", 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                    return cfg.get("path")
            except: pass
        return None 

    def on_backup_clicked(self):
        success, res = BackupManager.create_backup(self._get_eden_exe())
        if success:
            # Update status immediately
            self.update_last_backup_status()
            
            # Show Dialog as requested
            w = MessageBox(
                self.lang.get("backup_saved_title", "Success"),
                self.lang.get("backup_saved_msg", "Saved to:\n{}").format(res),
                self
            )
            w.yesButton.setText(self.lang.get("open_backup_folder", "Open Folder"))
            w.cancelButton.setText(self.lang.get("ok", "OK"))
            
            if w.exec():
                self.open_backup_folder()
                
        else:
            InfoBar.error(
                title=self.lang.get("backup_failed", "Backup Failed"),
                content=res,
                parent=self,
                duration=3000
            )

    def open_backup_folder(self):
        root = BackupManager.get_backup_root()
        if root.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(root)))
        else:
            InfoBar.warning(title=self.lang.get("not_found", "Not Found"), content=str(root), parent=self)

    def on_restore_clicked(self):
        root = BackupManager.get_backup_root()
        if not root.exists() or not any(root.glob("*.zip")):
            InfoBar.warning(title=self.lang.get("no_backups_found", "No Backups Found"), content="", parent=self, duration=2000)
            return

        dialog = RestoreDialog(self)
        if dialog.exec():
            path = dialog.get_selected_path()
            if dialog.result() == 1 and path: # 1 is Accepted, but exec returns boolean usually for Dialog? MessageBoxBase inherits Dialog.
                 pass # Logic handled in dialog actions usually or here?
                 # Wait, logic moved inside dialog? No, I see success logic duplicated? 
                 # Ah, RestoreDialog is just a list. 
                 # My previous implementation had button connection inside dialog logic? No.
                 # Let's check: RestoreDialog inherits MessageBoxBase.
                 # MessageBoxBase 'yesButton' (Restore) accepts the dialog.
            
            if path:
                # Double Confirm
                w = MessageBox(
                    self.lang.get("warning", "Warning"), 
                    self.lang.get("restore_confirm", "Overwrite?"), 
                    self
                )
                if w.exec():
                    success, msg = BackupManager.restore_backup(path, self._get_eden_exe())
                    if success:
                        InfoBar.success(title=self.lang.get("restore_success", "Restored"), content="", parent=self, duration=3000)
                    else:
                        InfoBar.error(title=self.lang.get("restore_failed", "Restore Failed"), content=msg, parent=self, duration=3000)

    def update_ui_texts(self, lang_code):
        self.lang = LANG_MAP[lang_code]
        # Re-init cards to update text
        # Clean layout
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
            
        self.init_cards()

    def update_keys_status(self):
        status = KeysManager.get_key_status(self._get_eden_exe())
        prod = status['prod.keys']
        title = status['title.keys']
        
        p_str = self.lang.get("keys_status_found" if prod else "keys_status_missing")
        t_str = self.lang.get("keys_status_found" if title else "keys_status_missing")
        
        self.keysCard.set_status(self.lang.get("keys_status_template", "prod.keys: {} | title.keys: {}").format(p_str, t_str))

    def on_import_keys(self):
        img_path, _ = QFileDialog.getOpenFileName(
            self, 
            self.lang.get("import_keys", "Import Keys"),
            "",
            "Key Files (*.keys)"
        )
        if img_path:
            success, msg = KeysManager.import_key_file(img_path, self._get_eden_exe())
            if success:
                self.update_keys_status()
                InfoBar.success(self.lang.get("keys_imported"), msg, parent=self)
            else:
                InfoBar.error(self.lang.get("keys_import_failed"), msg, parent=self)

    def on_auto_scan_keys(self):
        found = KeysManager.auto_detect_keys()
        if not found:
            InfoBar.warning(title=self.lang.get("no_keys_found"), content="", parent=self)
            return
            
        # Ask to import
        msg = self.lang.get("scan_result", "Found {} keys").format(len(found))
        w = MessageBox(self.lang.get("auto_scan_keys"), msg, self.window())
        if w.exec():
            count = 0
            for p in found:
                if KeysManager.import_key_file(p, self._get_eden_exe())[0]:
                    count += 1
            
            self.update_keys_status()
            InfoBar.success(self.lang.get("keys_imported"), self.lang.get("keys_imported_count", "Imported {} files").format(count), parent=self)

    def open_keys_folder(self):
        path = KeysManager.get_keys_dir(self._get_eden_exe())
        if path:
             if not path.exists():
                 try: path.mkdir(parents=True, exist_ok=True)
                 except: pass
             
             if path.exists():
                 QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
             else:
                 InfoBar.warning(self.lang.get("error", "Error"), self.lang.get("create_folder_fail", "Could not create folder: {}").format(path), parent=self)
    def get_eden_log_dir(self):
        """Get the Eden log directory based on platform."""
        if sys.platform == "win32":
            return Path(os.getenv('APPDATA')) / "eden" / "log"
        else:
            return Path.home() / ".local" / "share" / "eden" / "log"

    def open_log_folder(self):
        log_dir = self.get_eden_log_dir()
        if not log_dir.exists():
            try: log_dir.mkdir(parents=True, exist_ok=True)
            except: pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_dir)))

    def export_logs(self):
        log_dir = self.get_eden_log_dir()
        if not log_dir.exists():
            InfoBar.warning(
                title=self.lang.get("error", "Error"),
                content=f"No logs folder found at:\n{log_dir}",
                parent=self.window()
            )
            return

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"Eden_Logs_{timestamp}.zip"
        
        save_path, _ = QFileDialog.getSaveFileName(
            self.window(),
            self.lang.get("export_logs", "Export Logs"),
            filename,
            "Zip Files (*.zip)"
        )

        if save_path:
            try:
                with zipfile.ZipFile(save_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    has_files = False
                    for root, dirs, files in os.walk(log_dir):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, log_dir)
                            zipf.write(file_path, arcname)
                            has_files = True
                    
                if not has_files:
                     InfoBar.warning(self.lang.get("warning", "Warning"), self.lang.get("log_folder_empty", "Log folder is empty."), parent=self)
                else:
                    InfoBar.success(
                        title=self.lang.get("success", "Success"),
                        content=self.lang.get("log_export_success", "Logs exported.").format(save_path),
                        parent=self.window(),
                        duration=3000
                    )
            except Exception as e:
                logger.error(f"Failed to export logs: {e}")
                InfoBar.error(
                    title=self.lang.get("error", "Error"),
                    content=self.lang.get("log_export_fail", "Export failed.").format(str(e)),
                    parent=self.window(),
                    duration=3000
                )

