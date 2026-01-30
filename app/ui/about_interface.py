from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget

from qfluentwidgets import (SingleDirectionScrollArea, CardWidget, StrongBodyLabel, SubtitleLabel, BodyLabel, 
                           HyperlinkButton, PrimaryPushButton, FluentIcon as FIF, ImageLabel)

from app.config import LANG_MAP, CURRENT_VERSION
from app.utils.path_utils import get_resource_path

class AboutInterface(SingleDirectionScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName('aboutInterface')
        self.lang = LANG_MAP["en"]
        
        self.view = QWidget(self)
        self.view.setObjectName('view')
        # Make backgrounds transparent so global theme applies
        self.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        self.view.setStyleSheet("#view { background-color: transparent; }")
        
        self.vBoxLayout = QVBoxLayout(self.view)
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        
        self.vBoxLayout.setContentsMargins(36, 20, 36, 36)
        self.vBoxLayout.setSpacing(20)
        self.vBoxLayout.setAlignment(Qt.AlignTop)

        self.initHeader()
        self.initDescription()
        self.initCredits()
        self.initFooter()

    def initHeader(self):
        """Top banner with Logo and Version"""
        self.logoLabel = ImageLabel(get_resource_path("resources/logo.png"), self.view)
        self.logoLabel.setFixedSize(100, 100)
        
        self.titleLabel = SubtitleLabel("EmuMan", self.view)
        self.titleLabel.setStyleSheet("font-size: 32px; font-weight: bold; font-family: 'Segoe UI', 'Microsoft YaHei';")
        
        self.versionLabel = BodyLabel(f"Version {CURRENT_VERSION}", self.view)
        # Inherit color from theme, just set font size
        self.versionLabel.setStyleSheet("font-size: 14px; opacity: 0.8;")

        self.vBoxLayout.addWidget(self.logoLabel, 0, Qt.AlignCenter)
        self.vBoxLayout.addWidget(self.titleLabel, 0, Qt.AlignCenter)
        self.vBoxLayout.addWidget(self.versionLabel, 0, Qt.AlignCenter)
        self.vBoxLayout.addSpacing(10)

    def initDescription(self):
        """Project description and primary actions"""
        self.descLabel = BodyLabel("", self.view)
        self.descLabel.setAlignment(Qt.AlignCenter)
        self.descLabel.setWordWrap(True)
        # Remove hardcoded color #606060
        self.descLabel.setStyleSheet("font-size: 15px; line-height: 1.5;")
        
        # Action Buttons Row
        self.actionLayout = QHBoxLayout()
        self.actionLayout.setSpacing(15)
        self.actionLayout.setAlignment(Qt.AlignCenter)
        
        self.githubBtn = PrimaryPushButton(FIF.GITHUB, "Source Code", self.view)
        self.githubBtn.setFixedWidth(160)
        self.githubBtn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/pflyly/EmuMan")))
        
        self.issueBtn = HyperlinkButton(url="https://github.com/pflyly/EmuMan/issues", text="Report Issue", parent=self.view, icon=FIF.FEEDBACK)
        
        self.actionLayout.addWidget(self.githubBtn)
        self.actionLayout.addWidget(self.issueBtn)

        self.vBoxLayout.addWidget(self.descLabel)
        self.vBoxLayout.addSpacing(10)
        self.vBoxLayout.addLayout(self.actionLayout)
        self.vBoxLayout.addSpacing(20)

    def initCredits(self):
        """Credits Card"""
        self.creditsCard = CardWidget(self.view)
        self.cLayout = QVBoxLayout(self.creditsCard)
        self.cLayout.setContentsMargins(24, 24, 24, 24)
        
        self.creditsTitle = SubtitleLabel("", self.creditsCard)
        self.creditsTitle.setStyleSheet("font-size: 18px; margin-bottom: 10px;")
        
        self.cLayout.addWidget(self.creditsTitle)
        
        # List of components
        components = [
            ("Eden Emulator", "https://git.eden-emu.dev/eden-emu/eden", "Core Switch Emulator"),
            ("Aria2", "https://github.com/aria2/aria2", "High speed download utility"),
            ("PyQt-Fluent-Widgets", "https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6", "Modern UI Components"),
            ("NX Firmware", "https://github.com/THZoria/NX_Firmware", "Firmware Source"),
        ]
        
        for name, url, desc in components:
            row = QHBoxLayout()
            link = HyperlinkButton(url=url, text=name, parent=self.creditsCard)
            desc_lbl = BodyLabel(desc, self.creditsCard)
            # Use opacity instead of gray color for theme adaptability
            desc_lbl.setStyleSheet("opacity: 0.6;")
            
            row.addWidget(link)
            row.addStretch(1)
            row.addWidget(desc_lbl)
            self.cLayout.addLayout(row)

        self.vBoxLayout.addWidget(self.creditsCard)

    def initFooter(self):
        self.copyrightLabel = BodyLabel("", self.view)
        self.copyrightLabel.setAlignment(Qt.AlignCenter)
        self.copyrightLabel.setStyleSheet("opacity: 0.5; font-size: 12px; margin-top: 20px;")
        self.vBoxLayout.addWidget(self.copyrightLabel)

    def update_ui_texts(self, lang_code):
        self.lang = LANG_MAP.get(lang_code, LANG_MAP["en"])
        
        self.descLabel.setText(self.lang.get("project_desc", ""))
        self.githubBtn.setText(self.lang.get("view_on_github", "Source Code"))
        self.issueBtn.setText(self.lang.get("report_issue", "Report Issue"))
        self.creditsTitle.setText(self.lang.get("credits", "Credits"))
        self.copyrightLabel.setText(self.lang.get("copyright", ""))
