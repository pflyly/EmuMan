import os
import re
import sys
import json
import time
import shutil
import zipfile
from pathlib import Path

from app.utils.logger import get_logger
logger = get_logger(__name__)

import requests
from PySide6.QtCore import QObject, Signal, QThread

from app.utils.downloader import Downloader

class FirmwareUpdateCheckWorker(QThread):
    """异步检查固件更新的Worker"""
    finished = Signal(bool, str, str)  # has_update, latest_version, download_url
    
    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version
    
    def run(self):
        has_update, latest_version, download_url, _ = FirmwareManager.check_for_updates(self.current_version)
        self.finished.emit(has_update, latest_version or "", download_url or "")

class FirmwareInstallWorker(QThread):
    """后台线程：下载并安装固件"""
    progress = Signal(str, int, int, str)  # phase, current, total, speed
    finished = Signal(bool, str)  # success, message

    def __init__(self, download_url, eden_exe_path=None, version_tag=None):
        super().__init__()
        self.download_url = download_url
        self.eden_exe_path = eden_exe_path
        self.version_tag = version_tag
        self._is_cancelled = False

    def cancel(self):
        """Request cancellation"""
        self._is_cancelled = True

    def run(self):
        def progress_callback(phase, current, total, speed=""):
            if not self._is_cancelled:
                self.progress.emit(phase, current, total, speed)
        
        def cancel_check():
            return self._is_cancelled
        
        success, message = FirmwareManager.download_and_install(
            self.download_url,
            self.eden_exe_path,
            progress_callback,
            cancel_check,
            self.version_tag
        )
        
        if not self._is_cancelled:
            self.finished.emit(success, message)

class FirmwareManager(QObject):
    """Eden 模拟器固件管理"""
    install_progress = Signal(str, int, int, str)
    install_finished = Signal(bool, str)
    
    _file_cache = {}  # {path: (mtime, version)}

    def __init__(self):
        super().__init__()

    @staticmethod
    def _get_expected_sha256(version):
        """Get expected SHA256 from cache for verification."""
        cache_path = Path("cache") / "firmware_cache.json"
        if cache_path.exists():
            try:
                with open(cache_path, 'r') as f:
                    cache_data = json.load(f)
                    if cache_data.get("version") == version:
                        return cache_data.get("sha256")
            except: pass
        return None

    @staticmethod
    def get_firmware_path_config():
        """Get configured firmware download path."""
        default_path = os.path.abspath(os.path.join("downloads", "firmware"))
        if os.path.exists("config.json"):
            try:
                with open("config.json", 'r', encoding='utf-8') as f:
                    return json.load(f).get("firmware_path", default_path)
            except: pass
        return default_path

    @staticmethod
    def list_local_firmware():
        """List all .zip firmware files in the configured path."""
        path = FirmwareManager.get_firmware_path_config()
        if not os.path.exists(path):
            return []
        
        results = []
        try:
            for f in os.listdir(path):
                if f.lower().endswith(".zip"):
                    full_path = os.path.join(path, f)
                    size = os.path.getsize(full_path)
                    
                    # Extract version from filename
                    version = f # Default to filename
                    match = re.search(r"(\d+\.\d+\.\d+)", f)
                    if match:
                        version = match.group(1)
                        
                    results.append({
                        "name": f,
                        "version": version,
                        "path": full_path,
                        "size": size,
                        "size_str": f"{size / 1024 / 1024:.2f} MB"
                    })
            # Sort by name desc (usually higher version first)
            results.sort(key=lambda x: x['name'], reverse=True)
        except Exception as e:
            logger.error(f"Failed to list local firmware: {e}")
            
        return results

    @staticmethod
    def get_firmware_version(eden_exe_path=None):
        """
        读取固件版本
        优先比对本地记录与Eden日志，取较新的版本
        """
        # 1. 获取日志中的版本
        log_version = None
        log_time = 0
        
        log_paths = []
        if eden_exe_path and os.path.exists(eden_exe_path):
            exe_dir = Path(eden_exe_path).parent
            portable_log = exe_dir / "user" / "log" / "eden_log.txt"
            log_paths.append(portable_log)
        
        if sys.platform == "win32":
            system_log = Path.home() / "AppData" / "Roaming" / "eden" / "log" / "eden_log.txt"
        else:
            xdg_data_home = os.getenv("XDG_DATA_HOME")
            if xdg_data_home:
                system_log = Path(xdg_data_home) / "eden" / "log" / "eden_log.txt"
            else:
                system_log = Path.home() / ".local" / "share" / "eden" / "log" / "eden_log.txt"
        
        log_paths.append(system_log)
        
        for log_path in log_paths:
            if log_path.exists():
                try:
                    mtime = log_path.stat().st_mtime
                    
                    cached = FirmwareManager._file_cache.get(str(log_path))
                    if cached and cached[0] == mtime:
                        log_version = cached[1]
                        log_time = mtime
                        break

                    firmware_ver = FirmwareManager._parse_firmware_from_log(log_path)
                    if firmware_ver:
                        FirmwareManager._file_cache[str(log_path)] = (mtime, firmware_ver)
                        if not log_version or mtime > log_time:
                            log_version = firmware_ver
                            log_time = mtime
                except Exception as e:
                    logger.warning(f"Failed to read log file {log_path}: {e}")
        
        # 2. 获取本地记录的版本
        local_version, local_time = FirmwareManager._load_local_firmware_record()
        
        # 3. 比对并返回较新的版本
        if local_version and local_time > log_time:
            return local_version
            
        return log_version
    
    @staticmethod
    def _parse_firmware_from_log(log_path):
        """解析日志文件中的固件版本"""
        try:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    match = re.search(r'Installed firmware:\s*(\d+\.\d+\.\d+)', line)
                    if match:
                        return match.group(1)
        except Exception as e:
            logger.error(f"Error parsing firmware from {log_path}: {e}")
        
        return None
    
    @staticmethod
    def _save_local_firmware_record(version):
        """保存本地固件记录 (到 firmware_cache.json)"""
        try:
            cache_path = Path("cache") / "firmware_cache.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            if cache_path.exists():
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except: pass
            
            data["installed"] = {
                "version": version,
                "timestamp": time.time()
            }
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.warning(f"Failed to save local firmware record: {e}")

    @staticmethod
    def _load_local_firmware_record():
        """读取本地固件记录 (从 firmware_cache.json)"""
        try:
            cache_path = Path("cache") / "firmware_cache.json"
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        data = json.loads(content)
                        installed = data.get("installed", {})
                        return installed.get("version"), installed.get("timestamp", 0)
        except Exception as e:
            logger.warning(f"Failed to load local firmware record: {e}")
        return None, 0

    @staticmethod
    def get_display_text(eden_exe_path, lang_dict):
        firmware_version = FirmwareManager.get_firmware_version(eden_exe_path)
        
        if firmware_version:
            text = lang_dict.get("firmware_version", "Firmware: {}").format(firmware_version)
            
            # Check for update in cache
            try:
                cache_path = os.path.join("cache", "firmware_cache.json")
                cache = FirmwareManager._load_firmware_cache(cache_path)
                remote_ver = cache.get("version")
                
                if remote_ver and FirmwareManager._compare_versions(firmware_version, remote_ver):
                     text += lang_dict.get("firmware_update_hint", " (Update: {})").format(remote_ver)
            except Exception: pass
            
            return text, True
        
        return "", False
    
    @staticmethod
    def check_for_updates(current_version=None):
        """
        检查固件更新
        
        Returns:
            tuple: (has_update, latest_version, download_url, cache_updated)
        """
        cache_path = os.path.join("cache", "firmware_cache.json")
        
        try:
            cache_data = FirmwareManager._load_firmware_cache(cache_path)
            cached_version = cache_data.get("version")
            cached_url = cache_data.get("download_url")
            cache_time = cache_data.get("timestamp", 0)
            
            is_cache_valid = (time.time() - cache_time < 86400)
            
            if is_cache_valid and cached_version:
                if current_version and cached_version:
                    has_update = FirmwareManager._compare_versions(current_version, cached_version)
                    return has_update, cached_version, cached_url, False
                return False, cached_version, cached_url, False
            
            url = "https://api.github.com/repos/THZoria/NX_Firmware/releases/latest"
            headers = {
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'EmuMan-App-Client'
            }
            res = requests.get(url, headers=headers, timeout=8)
            
            if res.status_code == 200:
                data = res.json()
                remote_version = data.get("tag_name", "")
                assets = data.get("assets", [])
                download_url = None
                sha256 = None
                size = 0
                
                for asset in assets:
                    if asset['name'].lower().endswith('.zip'):
                        download_url = asset['browser_download_url']
                        size = asset.get('size', 0)
                        # Extract SHA256 from digest field (format: "sha256:xxxxx...")
                        digest = asset.get('digest', '')
                        if digest.startswith('sha256:'):
                            sha256 = digest[7:]  # Remove "sha256:" prefix
                        break
                
                FirmwareManager._save_firmware_cache(cache_path, remote_version, download_url, sha256, size)
                logger.info(f"Remote firmware info cached: {remote_version}")
                
                if current_version:
                    logger.info(f"Current local firmware version: {current_version}")
                    if remote_version:
                        has_update = FirmwareManager._compare_versions(current_version, remote_version)
                    return has_update, remote_version, download_url, True
                
                return False, remote_version, download_url, True
            else:
                if cached_version:
                    logger.warning(f"Failed to fetch firmware updates, using cached version: {cached_version}")
                    if current_version:
                        has_update = FirmwareManager._compare_versions(current_version, cached_version)
                        return has_update, cached_version, cached_url, False
                    return False, cached_version, cached_url, False
                return False, None, None, False
            
        except Exception as e:
            logger.warning(f"Firmware update check failed: {e}")
            cache_data = FirmwareManager._load_firmware_cache(cache_path)
            if cache_data.get("version"):
                cached_version = cache_data.get("version")
                cached_url = cache_data.get("download_url")
                if current_version:
                    has_update = FirmwareManager._compare_versions(current_version, cached_version)
                    return has_update, cached_version, cached_url, False
                return False, cached_version, cached_url, False
            return False, None, None, False
    
    @staticmethod
    def _load_firmware_cache(cache_path):
        if not os.path.exists(cache_path):
            return {}
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content: return {}
                return json.loads(content)
        except Exception as e:
            logger.warning(f"Failed to load firmware cache: {e}")
            try:
                os.remove(cache_path) # Auto-heal
            except: pass
            return {}
    
    @staticmethod
    def _save_firmware_cache(cache_path, version, download_url, sha256=None, size=0):
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            
            existing_data = {}
            if os.path.exists(cache_path):
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except: pass

            cache_data = {
                "version": version,
                "download_url": download_url,
                "sha256": sha256,
                "size": size,
                "timestamp": time.time()
            }
            
            existing_data.update(cache_data)
            
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save firmware cache: {e}")

    @staticmethod
    def verify_sha256(file_path, expected_sha256):
        """
        Verify SHA256 checksum of a file.
        
        Args:
            file_path: Path to the file to verify
            expected_sha256: Expected SHA256 hex string
            
        Returns:
            bool: True if checksum matches, False otherwise
        """
        if not expected_sha256:
            logger.warning("No SHA256 checksum available for verification")
            return True  # Skip verification if no checksum available
            
        try:
            import hashlib
            sha256_hash = hashlib.sha256()
            
            with open(file_path, "rb") as f:
                # Read in chunks to handle large files
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            
            calculated_sha256 = sha256_hash.hexdigest()
            
            if calculated_sha256 == expected_sha256:
                logger.info(f"SHA256 verification passed: {expected_sha256[:16]}...")
                return True
            else:
                logger.error(f"SHA256 mismatch! Expected: {expected_sha256}, Got: {calculated_sha256}")
                return False
                
        except Exception as e:
            logger.error(f"SHA256 verification failed: {e}")
            return False
    
    @staticmethod
    def _compare_versions(current, remote):
        try:
            curr_parts = [int(x) for x in current.split('.')]
            remote_parts = [int(x) for x in remote.split('.')]
            
            for c, r in zip(curr_parts, remote_parts):
                if r > c:
                    return True
                elif r < c:
                    return False
            
            return len(remote_parts) > len(curr_parts)
        except Exception:
            return False

    @staticmethod
    def get_nand_path(eden_exe_path=None):
        """
        获取 Eden 的 NAND registered 目录路径
        
        Priority:
        1. Portable: <exe_dir>/user/nand/system/Contents/registered/ (if <exe_dir>/user exists)
        2. System (Win): %APPDATA%/eden/nand/system/Contents/registered/
        3. System (Linux): ~/.local/share/eden/nand/system/Contents/registered/
        """
        if eden_exe_path and os.path.exists(eden_exe_path):
            path_obj = Path(eden_exe_path)
            # If input is directory (from settings), use it as exe_dir; if file (exe), use parent
            exe_dir = path_obj if path_obj.is_dir() else path_obj.parent
            
            # Check for Portable Mode (check 'user' folder)
            if (exe_dir / "user").exists():
                return exe_dir / "user" / "nand" / "system" / "Contents" / "registered"

        # System Mode Fallback
        if sys.platform == "win32":
            return Path.home() / "AppData" / "Roaming" / "eden" / "nand" / "system" / "Contents" / "registered"
        else:
            xdg_data_home = os.getenv("XDG_DATA_HOME")
            if xdg_data_home:
                return Path(xdg_data_home) / "eden" / "nand" / "system" / "Contents" / "registered"
            else:
                return Path.home() / ".local" / "share" / "eden" / "nand" / "system" / "Contents" / "registered"

    @staticmethod
    def get_user_data_path(eden_exe_path=None):
        """
        获取 Eden User 配置文件夹路径 (包含 keys, mod, nand 等)
        Portable: <exe_dir>/user
        System (Win): %APPDATA%/eden
        System (Linux): ~/.local/share/eden or $XDG_DATA_HOME/eden
        """
        if eden_exe_path and os.path.exists(eden_exe_path):
            path_obj = Path(eden_exe_path)
            exe_dir = path_obj if path_obj.is_dir() else path_obj.parent
            portable_user = exe_dir / "user"
            if portable_user.exists():
                return portable_user
        
        if sys.platform == "win32":
            return Path.home() / "AppData" / "Roaming" / "eden"
        else:
            xdg_data_home = os.getenv("XDG_DATA_HOME")
            if xdg_data_home:
                return Path(xdg_data_home) / "eden"
            else:
                return Path.home() / ".local" / "share" / "eden"

    @staticmethod
    def install_firmware(zip_path, eden_exe_path=None, progress_callback=None, cancel_check=None, version_tag=None):
        """
        安装固件到 Eden 的 NAND 目录
        
        Args:
            zip_path: 固件 ZIP 文件路径
            eden_exe_path: Eden 可执行文件路径（用于检测 portable 模式）
            progress_callback: 进度回调函数 (current, total)
            cancel_check: 取消检查回调，返回 True 则取消
            version_tag: 固件版本号
            
        Returns:
            tuple: (success, message, installed_count)
        """
        try:
            nand_path = FirmwareManager.get_nand_path(eden_exe_path)
            if not nand_path:
                return False, "Cannot determine NAND path", 0
            
            # Clean up existing files
            if nand_path.exists():
                logger.info(f"Cleaning existing firmware at: {nand_path}")
                try:
                    shutil.rmtree(nand_path)
                    # Re-create empty dir immediately
                    nand_path.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    logger.warning(f"Failed to clean firmware directory: {e}")
                    # Fallback to manual file deletion if rmtree fails
                    try:
                        for filename in os.listdir(nand_path):
                             file_path = nand_path / filename
                             if os.path.isfile(file_path):
                                 os.unlink(file_path)
                    except: pass

            nand_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Installing firmware to: {nand_path}")
            
            with zipfile.ZipFile(zip_path, 'r') as zf:
                if cancel_check and cancel_check():
                    return False, "Installation cancelled", 0
                    
                nca_files = [f for f in zf.namelist() if f.lower().endswith('.nca')]
                
                if not nca_files:
                    all_files = zf.namelist()
                    for item in all_files:
                        if '/' in item:
                            inner_path = '/'.join(item.split('/')[1:])
                            if inner_path.lower().endswith('.nca'):
                                nca_files.append(item)
                
                if not nca_files:
                    return False, "No NCA files found in firmware ZIP", 0
                
                total = len(nca_files)
                installed = 0
                
                for i, nca_file in enumerate(nca_files):
                    if cancel_check and cancel_check():
                        logger.info("Firmware installation cancelled by user")
                        return False, "Installation cancelled", installed
                        
                    if progress_callback:
                        progress_callback(i + 1, total)
                    
                    filename = os.path.basename(nca_file)
                    if not filename:
                        continue
                    
                    dest_path = nand_path / filename
                    
                    with zf.open(nca_file) as src:
                        with open(dest_path, 'wb') as dst:
                            shutil.copyfileobj(src, dst)
                    
                    installed += 1
                
                logger.info(f"Firmware installation complete: {installed} NCA files installed")
                    
                return True, f"Installed {installed} firmware files", installed
                
        except zipfile.BadZipFile:
            return False, "Invalid ZIP file", 0
        except PermissionError:
            return False, "Permission denied - close Eden first", 0
        except Exception as e:
            logger.error(f"Firmware installation failed: {e}")
            return False, str(e), 0

    @staticmethod
    def download_and_install(download_url, eden_exe_path=None, progress_callback=None, cancel_check=None, version_tag=None):
        """
        下载并安装固件 (使用统一 Downloader)
        
        Args:
            download_url: 固件下载 URL
            eden_exe_path: Eden 可执行文件路径
            progress_callback: 进度回调 (phase, current, total)
                phase: 'download' 或 'install'
            cancel_check: 取消检查回调，返回 True 则取消
            version_tag: 固件版本号
                
        Returns:
            tuple: (success, message)
        """
        temp_dir = Path(FirmwareManager.get_firmware_path_config())
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            from urllib.parse import urlparse, unquote
            parsed_url = urlparse(download_url)
            filename = unquote(parsed_url.path.split('/')[-1])
            if not filename or not filename.endswith('.zip'):
                filename = f"firmware_{version_tag}.zip" if version_tag else "firmware.zip"
        except Exception as e:
            filename = f"firmware_{version_tag}.zip" if version_tag else "firmware.zip"
        
        zip_path = temp_dir / filename
        
        try:
            logger.info(f"Starting firmware download via Unified Downloader: {download_url}")
            logger.info(f"Saving to: {zip_path}")
            
            if progress_callback:
                progress_callback('download', 0, 100, "Connecting...")
            
            if not Downloader.download(download_url, zip_path, lambda phase, cur, tot, speed="": progress_callback('download', cur, tot, speed) if progress_callback else None, cancel_check):
                return False, "Download failed or cancelled"
            
            logger.info(f"Firmware downloaded: {zip_path}")
            
            # Verify SHA256 checksum if enabled
            verify_checksum = True
            if os.path.exists("config.json"):
                try:
                    with open("config.json", 'r', encoding='utf-8') as f:
                        verify_checksum = json.load(f).get("verify_firmware_checksum", True)
                except Exception as e:
                    logger.warning(f"Failed to read verify_firmware_checksum setting: {e}")
            
            if verify_checksum:
                expected_sha256 = FirmwareManager._get_expected_sha256(version_tag)
                
                if expected_sha256:
                    logger.info(f"Verifying firmware integrity (Expected: {expected_sha256})...")
                    if progress_callback:
                        progress_callback('verifying', 0, 0, "Verifying (SHA256)...")
                    
                    if not FirmwareManager.verify_sha256(str(zip_path), expected_sha256):
                        try:
                            os.remove(zip_path)
                            logger.warning("Corrupted firmware deleted after failed verification.")
                        except: pass
                        return False, "Firmware checksum verification failed. File may be corrupted."
                    logger.info("Firmware integrity verified.")
                else:
                    logger.info("No SHA256 checksum found in cache, skipping verification.")
            
            def install_progress(current, total):
                if progress_callback:
                    progress_callback('install', current, total, "")
            
            success, msg, count = FirmwareManager.install_firmware(
                str(zip_path), 
                eden_exe_path, 
                install_progress,
                cancel_check,
                version_tag
            )
            
            if success:
                FirmwareManager._file_cache.clear()
            
            return success, msg
            
        except Exception as e:
            logger.error(f"Firmware update failed: {e}")
            return False, str(e)
        finally:
            should_keep = False
            try:
                if os.path.exists("config.json"):
                    with open("config.json", 'r', encoding='utf-8') as f:
                        cfg = json.load(f)
                        should_keep = cfg.get("keep_firmware_archive", False)
            except Exception as e:
                logger.warning(f"Failed to read keep_firmware_archive setting: {e}")
            
            if not should_keep:
                try:
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir)
                        logger.info(f"Cleaned up temporary firmware directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary directory: {e}")
            else:
                logger.info(f"Kept firmware archive as per user setting: {temp_dir}")

