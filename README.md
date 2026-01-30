<div align="center">
  <img src="resources/logo.png" alt="EmuMan Logo" width="128">
  <h1>EmuMan</h1>
  <p>A Simple, Powerful, and Elegant Multi-Version Manager for Eden Emulator</p>

  [![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
  [![PySide6](https://img.shields.io/badge/UI-PySide6-green.svg)](https://doc.qt.io/qtforpython/)
  [![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)
  [![Platform](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()
</div>

---

## 🌟 Introduction

**EmuMan** (Emulator Manager) is a helper utility specifically designed for the Eden Emulator. It addresses common pain points such as frequent emulator updates, complex firmware management, and difficult save data backups by providing a one-stop maintenance solution for players.

> [!TIP]
> **Stay Informed & Secure**: EmuMan puts the latest Eden changelogs front and center, so you always know what's new. Whether you're chasing the latest features or sticking to stability, switch branches effortlessly while keeping your saves safe.

---

## ✨ Core Features

- 🚀 **Multi-Version Management**: Automatic downloading, installation, and quick switching between Master (Stable) and Nightly (Dev) branches.
- 📦 **Firmware & Keys Management**: Automatically sync the latest firmware or install local files. One-click scanning and importing for `*.keys`.
- 🛡️ **Safe Backup**: Integrated "Save Manager" with multi-point backup and restore functionality—never worry about losing saves during updates.
- 🛠️ **Toolbox**: Useful utilities including log exporting and Mod (LayeredFS) toggle management.
- 🌍 **Multi-Language Support**: Native support for English, Chinese (Simplified/Traditional), Japanese, Korean, and more.
- 🎨 **Modern UI**: A high-quality native interface built with [PySide6-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets/tree/PySide6), featuring smooth Light/Dark mode transitions.

---

## 🚀 Quick Start

### Option 1: Run from Source (Recommended for Developers)

1. **Prerequisites (Linux Only)**:
   ```bash
   # Debian/Ubuntu
   sudo apt install aria2 python3-venv python3-pip
   # Arch Linux
   sudo pacman -S aria2 python-pip
   ```

2. **Clone the Repo**:
   ```bash
   git clone https://github.com/pflyly/EmuMan.git
   cd EmuMan
   ```

3. **Create and Activate Virtual Environment**:
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # Linux/macOS
   source .venv/bin/activate
   ```

4. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Launch Application**:
   ```bash
   python main.py
   ```

### Option 2: Run Pre-compiled Version (Coming Soon)

Please visit the [Releases](https://github.com/pflyly/EmuMan/releases) page to download the latest `.exe` installer.

---

## 📄 License

Distributed under the **MIT License**. See [LICENSE](LICENSE) for more information.

---

<div align="center">
  <p>If you find EmuMan helpful, please give us a ⭐️!</p>
  <p>Copyright © 2026 EmuMan </p>
</div>
