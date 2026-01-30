import os
import json
import time
import hashlib
import requests
from typing import Dict, Optional
from PySide6.QtCore import QObject, Signal, QThread

from app.utils.logger import get_logger
logger = get_logger(__name__)

# Worker Thread for Sync
class SyncWorker(QThread):
    finished = Signal(dict)
    error = Signal(str, str)
    
    def __init__(self, old_data=None, master_repo="eden-emulator/Releases", nightly_repo="pflyly/eden-nightly"):
        super().__init__()
        self.old_data = old_data or {}
        self.master_repo = master_repo
        self.nightly_repo = nightly_repo

    def run(self):
        token = "" # Optional token
        
        headers = {'Accept': 'application/vnd.github.v3+json'}
        # Try to load token from config (simple check)
        # Try to load token and limit from config
        fetch_limit = 15
        if os.path.exists("config.json"):
             try:
                 with open("config.json", 'r', encoding='utf-8') as f:
                     cfg = json.load(f)
                     if cfg.get("gh_token"):
                         headers['Authorization'] = f'token {cfg["gh_token"]}'
                     fetch_limit = cfg.get("fetch_limit", 15)
             except: pass

        res_data = {"changelogs": {"master": {}, "nightly": {}}, "versions": {"master": [], "nightly": []}}
        failed_branches = []
        fetch_log_success = True

        # --- Master ---
        try:
            url = f"https://api.github.com/repos/{self.master_repo}/releases?per_page={fetch_limit}"
            logger.info(f"Fetching Master releases from: {url}")
            m_res = requests.get(url, headers=headers, timeout=8)
            m_res.raise_for_status()
            if m_res.status_code == 200:
                m_data = m_res.json()
                logger.info(f"Master API Success. Found {len(m_data)} releases.")
                res_data["versions"]["master"] = [r['tag_name'] for r in m_data]
                res_data["assets"] = res_data.get("assets", {})
                for r in m_data:
                    tag = r['tag_name']
                    res_data["assets"][tag] = [{"name": a['name'], "browser_download_url": a['browser_download_url'], "size": a['size']} for a in r.get('assets', [])]
                    body = r.get('body', '').split("# Packages")[0].strip()
                    res_data["changelogs"]["master"][tag] = body
        except Exception as e:
            fetch_log_success = False
            failed_branches.append("Master")
            logger.error(f"Fetch Master failed: {e}")

        # --- Nightly ---
        try:
            url = f"https://api.github.com/repos/{self.nightly_repo}/releases?per_page={fetch_limit}"
            logger.info(f"Fetching Nightly releases from: {url}")
            n_res = requests.get(url, headers=headers, timeout=8)
            n_res.raise_for_status()
            if n_res.status_code == 200:
                n_data = n_res.json()
                logger.info(f"Nightly API Success. Found {len(n_data)} releases.")
                res_data["versions"]["nightly"] = [r['tag_name'] for r in n_data]
                if "assets" not in res_data: res_data["assets"] = {}
                for r in n_data:
                    tag = r['tag_name']
                    res_data["assets"][tag] = [{"name": a['name'], "browser_download_url": a['browser_download_url'], "size": a['size']} for a in r.get('assets', [])]
                    
                    # Robust Changelog Extraction
                    body = r.get('body', '')
                    clean_body = body[:800]
                    start_marks = ["## Changelog:", "### Changelog:", "## 更新日志:"]
                    start_idx = -1
                    for mark in start_marks:
                        start_idx = body.find(mark)
                        if start_idx != -1: break
                    if start_idx != -1:
                        end_idx = body.find("##", start_idx + 5)
                        clean_body = body[start_idx:end_idx].strip() if end_idx != -1 else body[start_idx:].strip()
                    
                    clean_body = clean_body.replace("**\n", "**\n\n")
                    res_data["changelogs"]["nightly"][tag] = clean_body
        except Exception as e:
            fetch_log_success = False
            failed_branches.append("Nightly")
            logger.error(f"Fetch Nightly failed: {e}")

        if failed_branches:
            # Fallback Logic using passed old_data
            if self.old_data:
                if not res_data["versions"]["master"] and self.old_data.get("versions", {}).get("master"):
                    res_data["versions"]["master"] = self.old_data["versions"]["master"]
                    res_data["changelogs"]["master"] = self.old_data.get("changelogs", {}).get("master", {})
                if not res_data["versions"]["nightly"] and self.old_data.get("versions", {}).get("nightly"):
                    res_data["versions"]["nightly"] = self.old_data["versions"]["nightly"]
                    res_data["changelogs"]["nightly"] = self.old_data.get("changelogs", {}).get("nightly", {})
                if self.old_data.get("assets"):
                    if "assets" not in res_data: res_data["assets"] = {}
                    res_data["assets"].update(self.old_data["assets"])
            return

        res_data["success"] = fetch_log_success
        self.finished.emit(res_data)

class CacheManager(QObject):
    sync_started = Signal()
    sync_finished = Signal(dict)
    sync_error = Signal(str)

    def __init__(self, cache_dir="cache", cache_file="eden_cache.json"):
        super().__init__()
        self.cache_dir = cache_dir
        self.cache_path = os.path.join(cache_dir, cache_file)
        self.scan_cache_file = os.path.join(cache_dir, "scan_cache.json")
        self.dir_hash_cache_file = os.path.join(cache_dir, "dir_hashes.json")
        
        self.sync_worker = None
        
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            
    def start_sync_task(self, force=False):
        """Starts the data synchronization thread."""
        is_fresh, old_data = self.is_cache_fresh()
        
        # If cache is fresh and not forced, return immediately (optimization)
        if is_fresh and not force and old_data:
             logger.info("Using fresh cached API data.")
             self.sync_finished.emit(old_data)
             return

        if self.sync_worker and self.sync_worker.isRunning():
            logger.warning("Sync already in progress.")
            return

        self.sync_started.emit()
        # Pass old_data for fallback purposes
        self.sync_worker = SyncWorker(old_data=old_data)
        self.sync_worker.finished.connect(self._on_worker_finished)
        self.sync_worker.error.connect(lambda t, m: self.sync_error.emit(f"{t}: {m}"))
        self.sync_worker.start()

    def _on_worker_finished(self, data):
        """Handle data from worker, save to cache, and notify UI."""
        if data.get("success", False):
            self.save_cache(data)
        self.sync_finished.emit(data)

    def load_cache(self):
        """Load cache data if it exists."""
        if not os.path.exists(self.cache_path):
            return None
        
        try:
            with open(self.cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None

    def save_cache(self, data):
        """Save data to cache with current timestamp."""
        try:
            cache_data = {
                "timestamp": time.time(),
                "data": data
            }
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save cache: {e}")

    def is_cache_fresh(self, max_age=3600):
        """Check if cache exists and is fresh."""
        data = self.load_cache()
        if not data:
            return False, None
        
        timestamp = data.get("timestamp", 0)
        content = data.get("data")
        
        if time.time() - timestamp < max_age:
            return True, content
        return False, content


    def _get_directory_hash(self, base_path: str) -> str:
        """Calculate directory hash to detect changes."""
        if not os.path.exists(base_path): return ""
        try:
            items = []
            for item in sorted(os.listdir(base_path)):
                item_path = os.path.join(base_path, item)
                if os.path.isdir(item_path):
                    stat = os.stat(item_path)
                    items.append(f"dir:{item}:{int(stat.st_mtime)}")
                else:
                    if not item.lower().endswith(('.zip', '.7z')):
                        stat = os.stat(item_path)
                        items.append(f"file:{item}:{stat.st_size}:{int(stat.st_mtime)}")
            content = "|".join(items)
            return hashlib.md5(content.encode()).hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate dir hash: {e}")
            return ""

    def is_scan_cache_valid(self, base_path: str, branch: str) -> bool:
        """Check if scan cache is valid based on directory hash."""
        if not base_path or not os.path.exists(base_path): return False
        
        current_hash = self._get_directory_hash(base_path)
        if not current_hash: return False
        
        try:
            if os.path.exists(self.dir_hash_cache_file):
                with open(self.dir_hash_cache_file, 'r', encoding='utf-8') as f:
                    hash_data = json.load(f)
                stored = hash_data.get(f"{base_path}:{branch}")
                if stored == current_hash: return True
        except Exception: pass
        return False

    def update_directory_hash(self, base_path: str, branch: str):
        """Update directory hash in cache."""
        current_hash = self._get_directory_hash(base_path)
        if not current_hash: return
        try:
            data = {}
            if os.path.exists(self.dir_hash_cache_file):
                with open(self.dir_hash_cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data[f"{base_path}:{branch}"] = current_hash
            with open(self.dir_hash_cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception: pass

    def get_cached_scan_result(self, base_path: str, branch: str) -> Optional[Dict]:
        """Retrieve cached scan result."""
        try:
            if os.path.exists(self.scan_cache_file):
                with open(self.scan_cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get(f"{base_path}:{branch}")
        except Exception: pass
        return None

    def save_scan_result(self, base_path: str, branch: str, result: Dict):
        """Save scan result and update directory hash."""
        try:
            data = {}
            if os.path.exists(self.scan_cache_file):
                with open(self.scan_cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            
            data[f"{base_path}:{branch}"] = {
                "result": result,
                "timestamp": time.time()
            }
            with open(self.scan_cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            self.update_directory_hash(base_path, branch)
        except Exception as e:
            logger.error(f"Failed to save scan result: {e}")

    def invalidate_scan_cache(self, base_path: str, branch: str):
        """Invalidate scan cache for specific path/branch."""
        key = f"{base_path}:{branch}"
        for fpath in [self.scan_cache_file, self.dir_hash_cache_file]:
            if os.path.exists(fpath):
                try:
                    with open(fpath, 'r', encoding='utf-8') as f: d = json.load(f)
                    if key in d:
                        del d[key]
                        with open(fpath, 'w', encoding='utf-8') as f: json.dump(d, f, indent=2)
                except Exception: pass
