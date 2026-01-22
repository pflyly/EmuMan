import os
import json
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QFileDialog, QWidget, 
                               QGridLayout, QSizePolicy)

from app.utils.logger import get_logger
logger = get_logger(__name__)
from qfluentwidgets import (CardWidget, StrongBodyLabel, SubtitleLabel, BodyLabel, ComboBox, LineEdit, PushButton, 
                            SwitchButton, FluentIcon as FIF, ScrollArea, IconWidget,
                            setTheme, setThemeColor, Theme, setFont, TransparentToolButton)

from app.config import LANG_MAP

class SettingRow(QWidget):
    """A single row setting: Title + Control"""
    def __init__(self, title, control, parent=None):
        super().__init__(parent)
        self.h_layout = QHBoxLayout(self)
        self.h_layout.setContentsMargins(0, 5, 0, 5)
        
        self.titleLabel = BodyLabel(title, self)
        
        self.h_layout.addWidget(self.titleLabel)
        self.h_layout.addStretch(1)
        self.h_layout.addWidget(control)
        
    def setTitle(self, title):
        self.titleLabel.setText(title)

class PathSettingRow(QWidget):
    """A path setting row: Title + Edit + Browse"""
    def __init__(self, title, edit, browseBtn, parent=None):
        super().__init__(parent)
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(0, 5, 0, 5)
        self.v_layout.setSpacing(5)

        self.titleLabel = BodyLabel(title, self)
        
        self.h_layout = QHBoxLayout()
        self.h_layout.setContentsMargins(0,0,0,0)
        self.h_layout.addWidget(edit, 1)
        self.h_layout.addWidget(browseBtn)
        
        self.v_layout.addWidget(self.titleLabel)
        self.v_layout.addLayout(self.h_layout)

    def setTitle(self, title):
        self.titleLabel.setText(title)

class SettingGroupCard(CardWidget):
    """Large Tile Card containing multiple settings"""
    def __init__(self, icon, title, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.mainLayout = QVBoxLayout(self)
        self.mainLayout.setContentsMargins(20, 20, 20, 20)
        self.mainLayout.setSpacing(15)

        # Header
        self.headerLayout = QHBoxLayout()
        
        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(32, 32)
        
        self.titleLabel = StrongBodyLabel(title, self)
        setFont(self.titleLabel, 16)
        
        self.headerLayout.addWidget(self.iconWidget, 0, Qt.AlignVCenter)
        self.headerLayout.addSpacing(10)
        self.headerLayout.addWidget(self.titleLabel, 0, Qt.AlignVCenter)
        self.headerLayout.addStretch(1)
        
        self.mainLayout.addLayout(self.headerLayout)
        
        # Content Container
        self.contentWidget = QWidget()
        self.contentLayout = QVBoxLayout(self.contentWidget)
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setSpacing(10)
        
        self.mainLayout.addWidget(self.contentWidget)
        self.mainLayout.addStretch(1)

    def addSetting(self, widget):
        self.contentLayout.addWidget(widget)

    def setTitle(self, title):
        self.titleLabel.setText(title)

class SettingInterface(QFrame):

    LANG_CODES = ["en", "zh", "cht", "ja", "ko", "ru", "pt", "fr"]

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName('settingInterface')
        self.config_file = "config.json"
        
        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Scroll Area
        self.scrollArea = ScrollArea(self)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        self.scrollWidget = QWidget()
        self.scrollWidget.setStyleSheet("QWidget { background: transparent; }")
        self.scrollArea.setWidget(self.scrollWidget)
        
        self.layout.addWidget(self.scrollArea)

        # Grid Layout for Groups
        self.gridLayout = QGridLayout(self.scrollWidget)
        self.gridLayout.setContentsMargins(36, 36, 36, 36)
        self.gridLayout.setSpacing(24)
        self.gridLayout.setAlignment(Qt.AlignTop)

        self.initAppGroup()
        self.initDownloadGroup()
        self.initPathGroup()
        
        self.load_config()
        self.connect_signals()

    def initAppGroup(self):
        self.appGroup = SettingGroupCard(FIF.BRUSH, LANG_MAP["en"]["settings_group_app"], self.scrollWidget)
        
        # Language
        self.langCombo = ComboBox()
        self.langCombo.addItems(["English", "简体中文", "繁體中文", "日本語", "한국어", "Русский", "Português", "Français"])
        self.langRow = SettingRow(LANG_MAP["en"]["lang"], self.langCombo)
        self.appGroup.addSetting(self.langRow)
        
        # Theme
        self.themeCombo = ComboBox()
        self.themeRow = SettingRow(LANG_MAP["en"]["theme_mode"], self.themeCombo)
        self.appGroup.addSetting(self.themeRow)

        # Check Update
        self.checkUpdateSwitch = SwitchButton()
        self.checkUpdateSwitch.setOnText(LANG_MAP["en"]["on"])
        self.checkUpdateSwitch.setOffText(LANG_MAP["en"]["off"])
        self.checkUpdateRow = SettingRow(LANG_MAP["en"]["check_update_start"], self.checkUpdateSwitch)
        self.appGroup.addSetting(self.checkUpdateRow)

        # Minimize to Tray
        self.minimizeToTraySwitch = SwitchButton()
        self.minimizeToTraySwitch.setOnText(LANG_MAP["en"]["on"])
        self.minimizeToTraySwitch.setOffText(LANG_MAP["en"]["off"])
        self.minimizeToTrayRow = SettingRow(LANG_MAP["en"]["minimize_to_tray"], self.minimizeToTraySwitch)
        self.appGroup.addSetting(self.minimizeToTrayRow)

        # Remember Selection
        self.rememberSelectionSwitch = SwitchButton()
        self.rememberSelectionSwitch.setOnText(LANG_MAP["en"]["on"])
        self.rememberSelectionSwitch.setOffText(LANG_MAP["en"]["off"])
        self.rememberSelectionRow = SettingRow(LANG_MAP["en"]["remember_last_selection"], self.rememberSelectionSwitch)
        self.appGroup.addSetting(self.rememberSelectionRow)

        # Fetch Limit
        self.fetchLimitCombo = ComboBox()
        self.fetchLimitCombo.addItems(["10", "15", "20", "25", "30"])
        self.fetchLimitRow = SettingRow(LANG_MAP["en"]["fetch_limit"], self.fetchLimitCombo)
        self.appGroup.addSetting(self.fetchLimitRow)
        self.gridLayout.addWidget(self.appGroup, 0, 0)

    def initDownloadGroup(self):
        self.dlGroup = SettingGroupCard(FIF.DOWNLOAD, LANG_MAP["en"]["settings_group_download"], self.scrollWidget)
        
        # Engine
        self.dlCombo = ComboBox()
        self.dlRow = SettingRow(LANG_MAP["en"]["downloader_engine"], self.dlCombo)
        self.dlGroup.addSetting(self.dlRow)
        
        # IPv6
        self.disableIPv6Switch = SwitchButton()
        self.disableIPv6Switch.setOnText(LANG_MAP["en"]["on"])
        self.disableIPv6Switch.setOffText(LANG_MAP["en"]["off"])
        self.ipv6Row = SettingRow(LANG_MAP["en"]["disable_ipv6"], self.disableIPv6Switch)
        self.dlGroup.addSetting(self.ipv6Row)
        
        # Aria2 Log
        self.aria2VerboseSwitch = SwitchButton()
        self.aria2VerboseSwitch.setOnText(LANG_MAP["en"]["on"])
        self.aria2VerboseSwitch.setOffText(LANG_MAP["en"]["off"])
        self.aria2Row = SettingRow(LANG_MAP["en"]["aria2_verbose_log"], self.aria2VerboseSwitch)
        self.dlGroup.addSetting(self.aria2Row)
        
        # Keep Archive
        self.keepArchiveSwitch = SwitchButton()
        self.keepArchiveSwitch.setOnText(LANG_MAP["en"]["on"])
        self.keepArchiveSwitch.setOffText(LANG_MAP["en"]["off"])
        self.keepArchiveRow = SettingRow(LANG_MAP["en"]["keep_archive"], self.keepArchiveSwitch)
        self.dlGroup.addSetting(self.keepArchiveRow)
        
        # Keep Firmware
        self.keepFirmwareSwitch = SwitchButton()
        self.keepFirmwareSwitch.setOnText(LANG_MAP["en"]["on"])
        self.keepFirmwareSwitch.setOffText(LANG_MAP["en"]["off"])
        self.keepFirmwareRow = SettingRow(LANG_MAP["en"]["keep_firmware_archive"], self.keepFirmwareSwitch)
        self.dlGroup.addSetting(self.keepFirmwareRow)

        # Verify Firmware
        self.verifyFirmwareSwitch = SwitchButton()
        self.verifyFirmwareSwitch.setOnText(LANG_MAP["en"]["on"])
        self.verifyFirmwareSwitch.setOffText(LANG_MAP["en"]["off"])
        self.verifyFirmwareRow = SettingRow(LANG_MAP["en"]["verify_firmware_checksum"], self.verifyFirmwareSwitch)
        self.dlGroup.addSetting(self.verifyFirmwareRow)
        self.gridLayout.addWidget(self.dlGroup, 0, 1)

    def initPathGroup(self):
        self.pathGroup = SettingGroupCard(FIF.FOLDER, LANG_MAP["en"]["settings_group_path"], self.scrollWidget)
        
        # Eden Path
        self.pathEdit = LineEdit()
        self.pathEdit.setReadOnly(True)
        self.browseBtn = PushButton(LANG_MAP["en"]["browse"], self, FIF.FOLDER)
        self.edenPathRow = PathSettingRow(LANG_MAP["en"]["eden_path"], self.pathEdit, self.browseBtn)
        self.pathGroup.addSetting(self.edenPathRow)
        
        # Backup Path
        self.backupPathEdit = LineEdit()
        self.backupPathEdit.setReadOnly(True)
        self.backupBrowseBtn = PushButton(LANG_MAP["en"]["browse"], self, FIF.FOLDER)
        self.backupPathRow = PathSettingRow(LANG_MAP["en"]["backup_path"], self.backupPathEdit, self.backupBrowseBtn)
        self.pathGroup.addSetting(self.backupPathRow)
        
        # Firmware Path
        self.firmwarePathEdit = LineEdit()
        self.firmwarePathEdit.setReadOnly(True)
        self.firmwareBrowseBtn = PushButton(LANG_MAP["en"]["browse"], self, FIF.FOLDER)
        self.firmwarePathRow = PathSettingRow(LANG_MAP["en"]["firmware_path"], self.firmwarePathEdit, self.firmwareBrowseBtn)
        self.pathGroup.addSetting(self.firmwarePathRow)
        self.gridLayout.addWidget(self.pathGroup, 1, 0, 1, 2) # Span full width

    def update_combo_items(self):
        """Update combo box texts"""
        try:
             lang = self.LANG_CODES[self.langCombo.currentIndex()]
        except: lang = "en"
        t = LANG_MAP[lang]
        
        # Theme
        self.themeCombo.blockSignals(True)
        old_idx = self.themeCombo.currentIndex()
        self.themeCombo.clear()
        self.themeCombo.addItems([t["theme_light"], t["theme_dark"], t["theme_auto"]])
        self.themeCombo.setCurrentIndex(max(0, old_idx))
        self.themeCombo.blockSignals(False)

        # Downloader
        self.dlCombo.blockSignals(True)
        old_dl_idx = self.dlCombo.currentIndex()
        self.dlCombo.clear()
        self.dlCombo.addItems([t["dl_auto"], t["dl_requests"]])
        self.dlCombo.setCurrentIndex(max(0, old_dl_idx))
        self.dlCombo.blockSignals(False)

    def update_ui_texts(self):
        try:
             lang = self.LANG_CODES[self.langCombo.currentIndex()]
        except: lang = "en"
        texts = LANG_MAP[lang]
        
        self.appGroup.setTitle(texts["settings_group_app"])
        self.langRow.setTitle(texts["lang"])
        self.themeRow.setTitle(texts["theme_mode"])
        self.checkUpdateRow.setTitle(texts["check_update_start"])
        self.minimizeToTrayRow.setTitle(texts["minimize_to_tray"])
        self.rememberSelectionRow.setTitle(texts["remember_last_selection"])
        self.fetchLimitRow.setTitle(texts["fetch_limit"])
        
        self.dlGroup.setTitle(texts["settings_group_download"])
        self.dlRow.setTitle(texts["downloader_engine"])
        self.ipv6Row.setTitle(texts["disable_ipv6"])
        self.aria2Row.setTitle(texts["aria2_verbose_log"])
        self.keepArchiveRow.setTitle(texts["keep_archive"])
        self.keepFirmwareRow.setTitle(texts["keep_firmware_archive"])
        self.verifyFirmwareRow.setTitle(texts["verify_firmware_checksum"])
        
        self.pathGroup.setTitle(texts["settings_group_path"])
        self.edenPathRow.setTitle(texts["eden_path"])
        self.backupPathRow.setTitle(texts["backup_path"])
        self.firmwarePathRow.setTitle(texts["firmware_path"])
        
        self.browseBtn.setText(texts["browse"])
        self.backupBrowseBtn.setText(texts["browse"])
        self.firmwareBrowseBtn.setText(texts["browse"])

        # Switches need manual update if text depends on lang (On/Off usually auto, but just in case)
        for switch in [self.checkUpdateSwitch, self.minimizeToTraySwitch, self.rememberSelectionSwitch, self.disableIPv6Switch, self.aria2VerboseSwitch, 
                       self.keepArchiveSwitch, self.keepFirmwareSwitch, self.verifyFirmwareSwitch]: 

             switch.setOnText(texts["on"])
             switch.setOffText(texts["off"])

        win = self.window()
        if win and hasattr(win, 'update_navigation_texts') and hasattr(win, 'settingInterface'):
             win.update_navigation_texts(lang)

    def on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Eden Folder", self.pathEdit.text() or "D:\\")
        if folder:
            folder = os.path.normpath(folder)
            self.pathEdit.setText(folder)
            logger.info(f"User changed Eden path to: {folder}")
            self.save_and_apply()
    
    def on_backup_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Backup Folder", self.backupPathEdit.text() or os.path.abspath("backups/saves"))
        if folder:
            folder = os.path.normpath(folder)
            self.backupPathEdit.setText(folder)
            logger.info(f"User changed backup path to: {folder}")
            self.save_and_apply()

    def on_firmware_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Firmware Folder", self.firmwarePathEdit.text() or os.path.abspath("downloads/firmware"))
        if folder:
            folder = os.path.normpath(folder)
            self.firmwarePathEdit.setText(folder)
            logger.info(f"User changed firmware path to: {folder}")
            self.save_and_apply()
    
    def connect_signals(self):
        self.langCombo.currentIndexChanged.connect(self.save_and_apply)
        self.themeCombo.currentIndexChanged.connect(self.save_and_apply)
        self.checkUpdateSwitch.checkedChanged.connect(self.save_and_apply)
        self.checkUpdateSwitch.checkedChanged.connect(self.save_and_apply)
        self.minimizeToTraySwitch.checkedChanged.connect(self.save_and_apply)
        self.rememberSelectionSwitch.checkedChanged.connect(self.save_and_apply)
        self.dlCombo.currentIndexChanged.connect(self.save_and_apply)
        self.fetchLimitCombo.currentIndexChanged.connect(self.save_and_apply)
        self.keepArchiveSwitch.checkedChanged.connect(self.save_and_apply)
        self.disableIPv6Switch.checkedChanged.connect(self.save_and_apply)
        self.aria2VerboseSwitch.checkedChanged.connect(self.save_and_apply)
        self.browseBtn.clicked.connect(self.on_browse)
        self.backupBrowseBtn.clicked.connect(self.on_backup_browse)
        self.firmwareBrowseBtn.clicked.connect(self.on_firmware_browse)
        self.keepFirmwareSwitch.checkedChanged.connect(self.save_and_apply)
        self.verifyFirmwareSwitch.checkedChanged.connect(self.save_and_apply)

    def get_current_config_dict(self):
        try:
             lang = self.LANG_CODES[self.langCombo.currentIndex()]
        except: lang = "en"
        
        theme_keys = ["Light", "Dark", "Auto"]
        try:
            theme_val = theme_keys[self.themeCombo.currentIndex()]
        except: theme_val = "Dark"
        
        check_update_val = self.checkUpdateSwitch.isChecked()
        minimize_tray_val = self.minimizeToTraySwitch.isChecked()
        remember_selection_val = self.rememberSelectionSwitch.isChecked()

        dl_val = "requests" if self.dlCombo.currentIndex() == 1 else "aria2"

        fetch_limit_val = self.fetchLimitCombo.currentText()

        keep_archive = self.keepArchiveSwitch.isChecked()

        disable_ipv6 = self.disableIPv6Switch.isChecked()

        aria2_verbose = self.aria2VerboseSwitch.isChecked()

        path = self.pathEdit.text()
        backup_path = self.backupPathEdit.text()
        firmware_path = self.firmwarePathEdit.text()
        keep_firmware = self.keepFirmwareSwitch.isChecked()
        verify_firmware = self.verifyFirmwareSwitch.isChecked()

        return {
            "lang": lang, 
            "theme": theme_val, 
            "check_update_at_start": check_update_val,
            "minimize_to_tray": minimize_tray_val,
            "remember_last_selection": remember_selection_val,
            "downloader_type": dl_val, 
            "fetch_limit": int(fetch_limit_val or "15"),
            "keep_archive": keep_archive,
            "disable_ipv6": disable_ipv6,
            "aria2_verbose_log": aria2_verbose,
            "path": path,
            "backup_path": backup_path,
            "firmware_path": firmware_path,
            "keep_firmware_archive": keep_firmware,
            "verify_firmware_checksum": verify_firmware
        }

    def save_config_to_file(self):
        cfg = self.get_current_config_dict()
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=4, ensure_ascii=False)
        return cfg

    def save_and_apply(self):
        # 1. Read current valid config to compare
        old_cfg = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    old_cfg = json.load(f)
            except: pass

        # 2. Get UI values
        cfg = self.get_current_config_dict()
        
        lang = cfg["lang"]
        theme_val = cfg["theme"]
        check_update_val = cfg["check_update_at_start"]
        minimize_tray_val = cfg["minimize_to_tray"]
        remember_selection_val = cfg["remember_last_selection"]
        dl_val = cfg["downloader_type"]
        fetch_limit_val = str(cfg["fetch_limit"])
        keep_archive = cfg["keep_archive"]
        disable_ipv6 = cfg["disable_ipv6"]
        aria2_verbose = cfg["aria2_verbose_log"]
        path = cfg["path"]
        backup_path = cfg["backup_path"]
        firmware_path = cfg["firmware_path"]
        keep_firmware = cfg["keep_firmware_archive"]
        verify_firmware = cfg["verify_firmware_checksum"]
        
        # 3. Detect Changes
        lang_changed = (lang != old_cfg.get("lang"))
        theme_changed = (theme_val != old_cfg.get("theme"))
        check_update_changed = (check_update_val != old_cfg.get("check_update_at_start", True))
        minimize_tray_changed = (minimize_tray_val != old_cfg.get("minimize_to_tray", False))
        remember_selection_changed = (remember_selection_val != old_cfg.get("remember_last_selection", True))
        dl_changed = (dl_val != old_cfg.get("downloader_type"))
        fetch_limit_changed = (fetch_limit_val != str(old_cfg.get("fetch_limit")))
        keep_archive_changed = (keep_archive != old_cfg.get("keep_archive"))
        disable_ipv6_changed = (disable_ipv6 != old_cfg.get("disable_ipv6"))
        aria2_verbose_changed = (aria2_verbose != old_cfg.get("aria2_verbose_log"))
        path_changed = (path != old_cfg.get("path"))
        backup_path_changed = (backup_path != old_cfg.get("backup_path"))
        firmware_path_changed = (firmware_path != old_cfg.get("firmware_path"))
        keep_firmware_changed = (keep_firmware != old_cfg.get("keep_firmware_archive"))
        verify_firmware_changed = (verify_firmware != old_cfg.get("verify_firmware_checksum"))

        # 4. Save
        self.save_config_to_file()

        # 5. Apply & Log
        if theme_changed:
            theme_obj = {"Light": Theme.LIGHT, "Dark": Theme.DARK, "Auto": Theme.AUTO}
            logger.info(f"User changed theme to: {theme_val}")
            setTheme(theme_obj[theme_val])

        if check_update_changed:
            logger.info(f"User changed check update start to: {check_update_val}")

        if minimize_tray_changed:
            logger.info(f"User changed minimize to tray to: {minimize_tray_val}")

        if remember_selection_changed:
            logger.info(f"User changed remember selection to: {remember_selection_val}")

        if dl_changed:
            logger.info(f"User changed downloader engine to: {dl_val}")

        if fetch_limit_changed:
            logger.info(f"User changed fetch limit to: {fetch_limit_val}")

        if keep_archive_changed:
            logger.info(f"User changed keep archive to: {keep_archive}")

        if disable_ipv6_changed:
            logger.info(f"User changed disable IPv6 to: {disable_ipv6}")

        if aria2_verbose_changed:
            logger.info(f"User changed Aria2 verbose logging to: {aria2_verbose}")

        if backup_path_changed:
            logger.info(f"User changed backup path to: {backup_path}")

        if keep_firmware_changed:
            logger.info(f"User changed keep firmware archive to: {keep_firmware}")
        
        if verify_firmware_changed:
            logger.info(f"User changed verify firmware checksum to: {verify_firmware}")

        if lang_changed or theme_changed or dl_changed:
            self.update_combo_items()
            self.update_ui_texts()
        
        win = self.window()
        if win:
            if hasattr(win, 'homeInterface'):
                 if lang_changed:
                     win.homeInterface.refresh_language(lang)
                     if hasattr(win, 'aboutInterface'):
                         win.aboutInterface.update_ui_texts(lang)
                         try:
                             about_key = win.aboutInterface.objectName()
                             current_about_text = LANG_MAP[lang]["about"]
                             if win.navigationInterface.widget(about_key):
                                 win.navigationInterface.widget(about_key).setText(current_about_text)
                         except: pass
                     
                     # Update Tray Menu
                     if hasattr(win, 'update_tray_texts'):
                         win.update_tray_texts(lang)

                     # Update Navigation Texts
                     if hasattr(win, 'update_navigation_texts'):
                         win.update_navigation_texts(lang)

                 if hasattr(win, 'toolsInterface'):
                     win.toolsInterface.update_ui_texts(lang)
                     try:
                         tools_key = win.toolsInterface.objectName()
                         if win.navigationInterface.widget(tools_key):
                             win.navigationInterface.widget(tools_key).setText(LANG_MAP[lang]["toolbox"])
                     except: pass
                 
                 if path_changed:
                     win.homeInterface.scan_local_versions()
                     win.homeInterface.update_status()
                     win.homeInterface.update_watcher_path()

    def load_config(self):
        self.update_combo_items()

        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)

                    # Lang
                    lang = cfg.get("lang", "en")
                    self.langCombo.blockSignals(True)
                    try:
                        idx = self.LANG_CODES.index(lang)
                        self.langCombo.setCurrentIndex(idx)
                    except ValueError:
                        self.langCombo.setCurrentIndex(0)
                    self.langCombo.blockSignals(False)

                    # Theme
                    theme_map = {"Light": 0, "Dark": 1, "Auto": 2}
                    theme_val = cfg.get("theme", "Dark")
                    self.themeCombo.blockSignals(True)
                    self.themeCombo.setCurrentIndex(theme_map.get(theme_val, 1))
                    self.themeCombo.blockSignals(False)
                    
                    theme_obj = {"Light": Theme.LIGHT, "Dark": Theme.DARK, "Auto": Theme.AUTO}
                    setTheme(theme_obj.get(theme_val, Theme.DARK))

                    # Check Update
                    check_update = cfg.get("check_update_at_start", True)
                    self.checkUpdateSwitch.blockSignals(True)
                    self.checkUpdateSwitch.setChecked(check_update)
                    self.checkUpdateSwitch.blockSignals(False)

                    # Minimize Tray
                    limit_tray = cfg.get("minimize_to_tray", False)
                    self.minimizeToTraySwitch.blockSignals(True)
                    self.minimizeToTraySwitch.setChecked(limit_tray)
                    self.minimizeToTraySwitch.blockSignals(False)

                    # Remember Selection
                    remember_selection = cfg.get("remember_last_selection", True)
                    self.rememberSelectionSwitch.blockSignals(True)
                    self.rememberSelectionSwitch.setChecked(remember_selection)
                    self.rememberSelectionSwitch.blockSignals(False)

                    # Downloader
                    dl_val = cfg.get("downloader_type", "aria2")
                    self.dlCombo.blockSignals(True)
                    self.dlCombo.setCurrentIndex(1 if dl_val == "requests" else 0)
                    self.dlCombo.blockSignals(False)

                    # Fetch Limit
                    fetch_limit = cfg.get("fetch_limit", "15")
                    limit_map = {"10": 0, "15": 1, "20": 2, "25": 3, "30": 4}
                    self.fetchLimitCombo.blockSignals(True)
                    self.fetchLimitCombo.setCurrentIndex(limit_map.get(str(fetch_limit), 1))
                    self.fetchLimitCombo.blockSignals(False)

                    # Keep Archive
                    keep_archive = cfg.get("keep_archive", False)
                    self.keepArchiveSwitch.blockSignals(True)
                    self.keepArchiveSwitch.setChecked(keep_archive)
                    self.keepArchiveSwitch.blockSignals(False)

                    # IPv6
                    disable_ipv6 = cfg.get("disable_ipv6", True)
                    self.disableIPv6Switch.blockSignals(True)
                    self.disableIPv6Switch.setChecked(disable_ipv6)
                    self.disableIPv6Switch.blockSignals(False)

                    # Aria2 Log
                    aria2_verbose = cfg.get("aria2_verbose_log", False)
                    self.aria2VerboseSwitch.blockSignals(True)
                    self.aria2VerboseSwitch.setChecked(aria2_verbose)
                    self.aria2VerboseSwitch.blockSignals(False)

                    self.pathEdit.setText(cfg.get("path", os.path.abspath("downloads/eden")))
                    
                    # Backup Path
                    backup_path = cfg.get("backup_path", os.path.abspath("backups/saves"))
                    self.backupPathEdit.setText(backup_path)
                    
                    # Firmware Path
                    firmware_path = cfg.get("firmware_path", os.path.abspath("downloads/firmware"))
                    self.firmwarePathEdit.setText(firmware_path)
                    
                    # Keep Firmware
                    keep_firmware = cfg.get("keep_firmware_archive", True)
                    self.keepFirmwareSwitch.blockSignals(True)
                    self.keepFirmwareSwitch.setChecked(keep_firmware)
                    self.keepFirmwareSwitch.blockSignals(False)

                    # Verify Firmware
                    verify_firmware = cfg.get("verify_firmware_checksum", True)
                    self.verifyFirmwareSwitch.blockSignals(True)
                    self.verifyFirmwareSwitch.setChecked(verify_firmware)
                    self.verifyFirmwareSwitch.blockSignals(False)
            except Exception as e:
                logger.warning(f"Failed to load config.json, using defaults. Error: {e}")
        else:
            # Default settings for fresh install
            setTheme(Theme.DARK)
            self.themeCombo.setCurrentIndex(1) # Default to Dark in UI
            self.dlCombo.setCurrentIndex(0) # Default to Aria2 (Auto)
            self.rememberSelectionSwitch.setChecked(True)
            self.fetchLimitCombo.setCurrentIndex(1) # 15
            self.disableIPv6Switch.setChecked(True)
            self.keepFirmwareSwitch.setChecked(True)
            self.verifyFirmwareSwitch.setChecked(True)

            # Default Paths & Auto-create
            default_eden = os.path.abspath("downloads/eden")
            default_backup = os.path.abspath("backups/saves")
            default_firmware = os.path.abspath("downloads/firmware")

            self.pathEdit.setText(default_eden)
            self.backupPathEdit.setText(default_backup)
            self.firmwarePathEdit.setText(default_firmware)

            for p in [default_eden, default_backup, default_firmware]:
                try:
                    os.makedirs(p, exist_ok=True)
                except Exception as e:
                    logger.error(f"Failed to create default directory {p}: {e}")

        self.update_ui_texts()
