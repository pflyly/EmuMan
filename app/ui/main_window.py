import os
import json
from PySide6.QtGui import QIcon, QAction, QCursor, QDesktopServices
from PySide6.QtCore import Qt, QUrl
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from qfluentwidgets import FluentWindow, FluentIcon as FIF, NavigationItemPosition

from app.core.firmware_manager import FirmwareManager
from app.utils.path_utils import get_resource_path

from app.config import LANG_MAP
from app.ui.home_interface import HomeInterface
from app.ui.tools_interface import ToolsInterface
from app.ui.setting_interface import SettingInterface
from app.ui.about_interface import AboutInterface

class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()

        self.navigationInterface.setMinimumWidth(50)
        self.navigationInterface.setExpandWidth(155)
        self.homeInterface = HomeInterface(self)
        self.toolsInterface = ToolsInterface(self)
        self.settingInterface = SettingInterface(self)
        self.aboutInterface = AboutInterface(self)
        
        self.settingInterface.load_config()
        self.homeInterface.scan_local_versions()
        self.initNavigation()
        
        self.settingInterface.update_ui_texts()
        # Initialize About texts based on loaded config from Settings
        try:
             lang_idx = self.settingInterface.langCombo.currentIndex()
             lang_code = self.settingInterface.LANG_CODES[lang_idx]
        except:
             lang_code = "en"
             
        self.aboutInterface.update_ui_texts(lang_code)
        self.toolsInterface.update_ui_texts(lang_code)
        self.update_navigation_texts(lang_code)

        self.initWindow()
        self.createTrayIcon()

    def initNavigation(self):
        self.addSubInterface(self.homeInterface, FIF.HOME, LANG_MAP["en"]["home"])
        self.addSubInterface(self.toolsInterface, FIF.APPLICATION, LANG_MAP["en"]["toolbox"])
        self.addSubInterface(self.settingInterface, FIF.SETTING, LANG_MAP["en"]["settings"])
        
        self.addSubInterface(self.aboutInterface, FIF.INFO, LANG_MAP["en"]["about"], position=NavigationItemPosition.BOTTOM)

    def initWindow(self):
        self.resize(1100, 800)
        self.setWindowTitle('EmuMan')
        
        # Resolve icon path
        icon_path = get_resource_path('resources/logo.png')
        self.setWindowIcon(QIcon(icon_path))
        
        screens = QApplication.screens()
        if screens:
            desktop = screens[0].availableGeometry()
            w, h = desktop.width(), desktop.height()
            self.move(w//2 - self.width()//2, h//2 - self.height()//2)

    def createTrayIcon(self):
        self.trayIcon = QSystemTrayIcon(self)
        self.trayIcon.setIcon(self.windowIcon())
        
        # Determine initial language
        lang_code = "en"
        if hasattr(self, 'settingInterface'):
             try:
                 lang_idx = self.settingInterface.langCombo.currentIndex()
                 lang_code = self.settingInterface.LANG_CODES[lang_idx]
             except: lang_code = "en"

        # Tray Menu
        self.trayMenu = QMenu()
        # Darker separator style
        self.trayMenu.setStyleSheet("""
            QMenu {
                background-color: #ffffff;
                border: 1px solid #e5e5e5;
            }
            QMenu::item {
                padding: 8px 30px;
            }
            QMenu::item:selected {
                background-color: #f0f0f0;
            }
            QMenu::separator {
                height: 1px;
                background-color: #A0A0A0;
                margin: 6px 15px; 
            }
        """)
        self.showAction = QAction(LANG_MAP[lang_code].get("tray_show", "Show EmuMan"), self)
        self.showAction.triggered.connect(self.showNormal)
        
        # Directory Menu
        self.openDirMenu = QMenu(LANG_MAP[lang_code].get("tray_open_dir", "Open Directory"), self.trayMenu)
        # Apply style to submenu too
        self.openDirMenu.setStyleSheet(self.trayMenu.styleSheet())
        
        self.openEdenDirAction = QAction(LANG_MAP[lang_code].get("tray_open_eden_dir", "Eden Emulator Dir"), self)
        self.openEdenDirAction.triggered.connect(self.on_open_eden_dir)
        
        self.openUserDirAction = QAction(LANG_MAP[lang_code].get("tray_open_user_dir", "Eden Settings Dir"), self)
        self.openUserDirAction.triggered.connect(self.on_open_user_dir)
        
        self.openFirmwareDirAction = QAction(LANG_MAP[lang_code].get("tray_open_firmware_dir", "Firmware Save Dir"), self)
        self.openFirmwareDirAction.triggered.connect(self.on_open_firmware_dir)
        
        self.openBackupDirAction = QAction(LANG_MAP[lang_code].get("tray_open_backup_dir", "Backup Save Dir"), self)
        self.openBackupDirAction.triggered.connect(self.on_open_backup_dir)
        
        self.openDirMenu.addAction(self.openEdenDirAction)
        self.openDirMenu.addAction(self.openUserDirAction)
        self.openDirMenu.addSeparator()
        self.openDirMenu.addAction(self.openFirmwareDirAction)
        self.openDirMenu.addAction(self.openBackupDirAction)
        
        self.launchMasterAction = QAction(LANG_MAP[lang_code].get("tray_launch_master", "Launch Master"), self)
        self.launchMasterAction.triggered.connect(self.launch_master)
        
        self.launchNightlyAction = QAction(LANG_MAP[lang_code].get("tray_launch_nightly", "Launch Nightly"), self)
        self.launchNightlyAction.triggered.connect(self.launch_nightly)
        
        self.quitAction = QAction(LANG_MAP[lang_code].get("tray_exit", "Exit"), self)
        self.quitAction.triggered.connect(QApplication.quit)
        
        self.trayMenu.addAction(self.showAction)
        self.trayMenu.addMenu(self.openDirMenu)
        self.trayMenu.addSeparator()
        self.trayMenu.addAction(self.launchMasterAction)
        self.trayMenu.addAction(self.launchNightlyAction)
        self.trayMenu.addSeparator()
        self.trayMenu.addAction(self.quitAction)
        
        self.trayIcon.activated.connect(self.onTrayIconActivated)
        self.trayIcon.show()
    
    def update_tray_texts(self, lang_code):
        """Update tray menu texts dynamically"""
        if hasattr(self, 'showAction'):
             self.showAction.setText(LANG_MAP[lang_code].get("tray_show", "Show EmuMan"))
             
             self.openDirMenu.setTitle(LANG_MAP[lang_code].get("tray_open_dir", "Open Directory"))
             self.openEdenDirAction.setText(LANG_MAP[lang_code].get("tray_open_eden_dir", "Eden Emulator Dir"))
             self.openUserDirAction.setText(LANG_MAP[lang_code].get("tray_open_user_dir", "Eden Settings Dir"))
             self.openFirmwareDirAction.setText(LANG_MAP[lang_code].get("tray_open_firmware_dir", "Firmware Save Dir"))
             self.openBackupDirAction.setText(LANG_MAP[lang_code].get("tray_open_backup_dir", "Backup Save Dir"))
             
             self.launchMasterAction.setText(LANG_MAP[lang_code].get("tray_launch_master", "Launch Master"))
             self.launchNightlyAction.setText(LANG_MAP[lang_code].get("tray_launch_nightly", "Launch Nightly"))
             self.quitAction.setText(LANG_MAP[lang_code].get("tray_exit", "Exit"))


    def update_navigation_texts(self, lang_code):
        """Update navigation bar texts and tooltips"""
        texts = LANG_MAP[lang_code]
        nav_map = {
            self.homeInterface.objectName(): texts["home"],
            self.toolsInterface.objectName(): texts["toolbox"],
            self.settingInterface.objectName(): texts["settings"],
            self.aboutInterface.objectName(): texts["about"]
        }
        
        for object_name, text in nav_map.items():
            if object_name in self.navigationInterface.panel.items:
                item_widget = self.navigationInterface.panel.items[object_name].widget
                item_widget.setText(text)
                item_widget.setToolTip(text)
                
        # Update Menu Button Tooltip
        if hasattr(self.navigationInterface.panel, 'menuButton'):
            self.navigationInterface.panel.menuButton.setToolTip(texts.get("open_navigation", "Open Navigation"))

    def on_open_eden_dir(self):
        if hasattr(self, 'homeInterface'):
            self.homeInterface.open_eden_folder()

    def on_open_user_dir(self):
        if hasattr(self, 'homeInterface'):
            self.homeInterface.open_user_data_folder()

    def on_open_firmware_dir(self):
        path = FirmwareManager.get_firmware_path_config()
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def on_open_backup_dir(self):
        default_path = os.path.abspath(os.path.join("downloads", "backup"))
        path = default_path
        if os.path.exists("config.json"):
            try:
                with open("config.json", 'r', encoding='utf-8') as f:
                    path = json.load(f).get("backup_path", default_path)
            except: pass
        
        if not os.path.exists(path):
            try: os.makedirs(path)
            except: pass
            
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def launch_master(self):
        if hasattr(self, 'homeInterface'):
            self.homeInterface.on_launch_clicked("master")

    def launch_nightly(self):
        if hasattr(self, 'homeInterface'):
            self.homeInterface.on_launch_clicked("nightly")

    def onTrayIconActivated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()
        elif reason == QSystemTrayIcon.Context:
            self.activateWindow()
            self.trayMenu.exec(QCursor.pos())

    def closeEvent(self, event):
        # Save current configuration state (including defaults on first run)
        self.settingInterface.save_config_to_file()

        # Save validation selections
        if hasattr(self, 'homeInterface'):
            self.homeInterface.save_selection_state()

        minimize_to_tray = self.settingInterface.minimizeToTraySwitch.isChecked()
        if minimize_to_tray:
            if self.isVisible():
                self.hide()
                event.ignore()
            else:
                event.accept()
        else:
            event.accept()
