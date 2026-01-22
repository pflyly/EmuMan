import os
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QIcon, QPixmap, QImage
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout

from app.utils.logger import get_logger
logger = get_logger(__name__)
from qfluentwidgets import (CardWidget, SubtitleLabel, 
                            ComboBox, TextBrowser, PushButton, PrimaryPushButton,
                            ImageLabel, FluentIcon as FIF, setFont, IconWidget)

SUCCESS_BUTTON_STYLE = """
QPushButton {
    background-color: #2ecc71;
    border: 1px solid #2ecc71;
    border-radius: 4px;
    padding: 8px 36px;
    text-align: center;
}
QPushButton:hover {
    background-color: #40d47e;
}
QPushButton:pressed {
    background-color: #27ae60;
}
"""

class ChannelCard(CardWidget):
    """Modular UI component for a single branch (Master or Nightly)."""
    
    launch_requested = Signal(str) # branch
    download_requested = Signal(str) # branch
    selection_changed = Signal(str) # category/branch
    
    def __init__(self, branch, parent=None):
        super().__init__(parent=parent)
        self.branch = branch
        self.lang = {}
        self.downloading_versions = set()
        self.setup_ui()
        
    def setup_ui(self):
        self.v_layout = QVBoxLayout(self)
        self.v_layout.setContentsMargins(20, 20, 20, 20)
        
        # 1. Header (Icon + Title)
        header = QHBoxLayout()
        icon_type = FIF.CERTIFICATE if self.branch == "master" else FIF.DEVELOPER_TOOLS
        icon_label = IconWidget(icon_type, self)
        icon_label.setFixedSize(24, 24)
        
        self.titleLabel = SubtitleLabel("Channel", self)
        setFont(self.titleLabel, 18)
        
        header.addWidget(icon_label)
        header.addSpacing(10)
        header.addWidget(self.titleLabel)
        header.addStretch(1)
        
        # 2. Status Label
        self.statusLabel = SubtitleLabel("Status: Unknown", self)
        setFont(self.statusLabel, 13)
        
        # 3. Combo Box (Version Selector)
        self.combo = ComboBox(self)
        self.combo.currentIndexChanged.connect(lambda: self.selection_changed.emit(self.branch))
        
        # 4. Changelog
        self.changelog = TextBrowser(self)
        self.changelog.setOpenExternalLinks(True)
        
        
        # 5. Action Buttons
        actions = QHBoxLayout()
        self.launchBtn = PrimaryPushButton("Launch", self, FIF.PLAY)
        self.launchBtn.clicked.connect(lambda: self.launch_requested.emit(self.branch))
        self.launchBtn.hide() # Default hidden
        
        self.downloadBtn = PrimaryPushButton("Download", self, FIF.DOWNLOAD)
        self.downloadBtn.clicked.connect(lambda: self.download_requested.emit(self.branch))
        self.downloadBtn.hide() # Default hidden
        
        # Enforce consistent height to prevent jumps during state changes
        self.launchBtn.setFixedHeight(32)
        self.downloadBtn.setFixedHeight(32)
        
        # Create a styled progress bar that matches the button dimensions
        from PySide6.QtWidgets import QProgressBar
        self.downloadProgressBar = QProgressBar(self)
        self.downloadProgressBar.setFixedHeight(32)
        self.downloadProgressBar.setRange(0, 100)
        self.downloadProgressBar.setValue(0)
        self.downloadProgressBar.setTextVisible(False)
        self.downloadProgressBar.setStyleSheet("""
            QProgressBar {
                border: 1px solid rgba(0, 0, 0, 0.1);
                border-radius: 4px;
                background-color: rgba(0, 0, 0, 0.05);
            }
            QProgressBar::chunk {
                background-color: #2ecc71;
                border-radius: 3px;
            }
        """)
        self.downloadProgressBar.hide()
        
        actions.addWidget(self.launchBtn)
        actions.addWidget(self.downloadBtn)
        actions.addWidget(self.downloadProgressBar)
        
        # Assembly
        self.v_layout.addLayout(header)
        self.v_layout.addSpacing(10)
        self.v_layout.addWidget(self.statusLabel)
        self.v_layout.addSpacing(10)
        self.v_layout.addWidget(self.combo)
        self.v_layout.addSpacing(15)
        self.v_layout.addWidget(self.changelog, 1)
        self.v_layout.addSpacing(15)
        self.v_layout.addSpacing(5)
        self.v_layout.addLayout(actions)

    def refresh_language(self, lang):
        self.lang = lang
        category_key = f"{self.branch}_branch"
        title_key = f"{self.branch}_channel"
        self.titleLabel.setText(self.lang.get(title_key, self.branch.capitalize()))
        self.launchBtn.setText(self.lang.get("launch", "Launch"))
        self.downloadBtn.setText(self.lang.get("download_btn", "Download"))
        self.update_ui_state()
        
        # Force update "Unknown" status if no tag selected
        if not self.combo.currentData():
             prefix = self.lang.get("status_prefix", "Current: ")
             unknown = self.lang.get("status_unknown", "Unknown")
             self.statusLabel.setText(f"{prefix}{unknown}")

    def update_data(self, tags, local_map, downloading_versions):
        self.tags = tags
        self.local_map = local_map
        self.downloading_versions = downloading_versions
        
        # Update Combo with logic
        old_tag = self.combo.currentData()
        self.combo.blockSignals(True)
        self.combo.clear()
        
        green_icon = FIF.ACCEPT.icon(color=QColor("#00FF9D"))
        # Use transparent image with Alpha Channel to ensure it is invisible but takes space
        img = QImage(16, 16, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        transparent_icon = QIcon(QPixmap.fromImage(img))
        
        for tag in tags:
            if tag in local_map:
                self.combo.addItem(tag, green_icon, userData=tag)
            else:
                self.combo.addItem(tag, transparent_icon, userData=tag)
        
        if old_tag:
            idx = self.combo.findData(old_tag)
            self.combo.setCurrentIndex(max(0, idx))
        else:
            self.combo.setCurrentIndex(0)
            
        self.combo.blockSignals(False)
        self.update_ui_state()

    def update_ui_state(self):
        tag = self.combo.currentData()
        if not tag: return
        
        is_installed = tag in self.local_map
        is_dl = tag in self.downloading_versions
        
        # Buttons visibility
        self.launchBtn.setVisible(is_installed and not is_dl)
        self.launchBtn.setEnabled(is_installed and not is_dl)
        self.launchBtn.setStyleSheet(SUCCESS_BUTTON_STYLE if is_installed else "")
        self.downloadBtn.setVisible(not is_installed and not is_dl)
        
        # Status Text
        prefix = self.lang.get("status_prefix", "Current: ")
        status_val = tag if is_installed else self.lang.get("status_not_installed", "Not Installed")
        self.statusLabel.setText(f"{prefix}{status_val}")

    def set_changelog(self, content):
        self.changelog.setMarkdown(content)

    def set_download_progress(self, progress):
        """
        Updates the download progress display.
        progress: 0-100, or -1 to reset.
        """
        if progress < 0 or progress >= 100:
            # Reset / Complete state - show button, hide progress bar
            self.downloadProgressBar.hide()
            self.downloadProgressBar.setValue(0)
            self.update_ui_state() # Will show/hide downloadBtn based on install state
        else:
            # Downloading state - hide button, show progress bar
            self.downloadBtn.hide()
            self.downloadProgressBar.setValue(progress)
            self.downloadProgressBar.show()
