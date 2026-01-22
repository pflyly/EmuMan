import os
import re
import sys
import json

from app.utils.logger import get_logger
logger = get_logger(__name__)

class VersionManager:
    """Handles local filesystem interactions and version identification for the emulator."""
    
    @staticmethod
    def get_short_version(name):
        """Extract simplified version tag from filenames or directory names."""
        if not name: return ""
        # Master style: v0.0.1
        m = re.search(r'v\d+\.\d+\.\d+(-rc\d+)?', name)
        if m: return m.group(0)
        # Nightly style: 2026-01-24
        d = re.search(r'\d{4}-\d{2}-\d{2}', name)
        if d: return d.group(0)
        # Fallback numeric (e.g. 28206)
        n = re.findall(r'\d{5,}', name)
        if n: return n[0]
        return name

    @staticmethod
    def is_item_for_branch(item_name, branch):
        """Check if a filename/directory name belongs to a specific branch."""
        if branch == "master":
            return bool(re.search(r'v\d+\.\d+\.\d+', item_name))
        else: # nightly
            return bool(re.search(r'\d{5,}', item_name))

    @staticmethod
    def find_executable(base_path, item_name):
        """Locate the actual emulator executable inside a directory or as a single file."""
        if not item_name: return None
        full_path = os.path.join(base_path, item_name)
        base_exe = "eden.exe" if sys.platform == "win32" else "eden"
        
        if os.path.isdir(full_path):
            exe = os.path.join(full_path, base_exe)
            if not os.path.exists(exe):
                # Try handling nested folders from deep extraction
                try:
                    sub = os.listdir(full_path)
                    if len(sub) == 1:
                        nested = os.path.join(full_path, sub[0], base_exe)
                        if os.path.exists(nested):
                            return nested
                except Exception:
                    pass
            return exe if os.path.exists(exe) else None
        else:
            # Case 2: Single file binary (e.g. Linux AppImage or executable)
            return full_path if os.path.exists(full_path) else None

    def sort_versions(self, version_list):
        """Sort semver-style strings."""
        def version_key(v):
            base_match = re.search(r'v(\d+)\.(\d+)\.(\d+)', v)
            if not base_match: return (0, 0, 0, 0)
            major, minor, patch = map(int, base_match.groups())
            rc_match = re.search(r'-rc(\d+)', v)
            rc_weight = int(rc_match.group(1)) if rc_match else 999
            return (major, minor, patch, rc_weight)
        return sorted(version_list, key=version_key, reverse=True)

    def get_local_list(self, branch, base_path, known_cloud_tags):
        """Scan directory and return mapping of {Tag: FolderName}."""
        if not base_path or not os.path.exists(base_path):
            return {}
        
        local_map = {}
        try:
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                is_dir = os.path.isdir(item_path)
                
                # Skip obvious archives
                if not is_dir and item.lower().endswith((".zip", ".7z", ".aria2")):
                    continue
                
                # Master validation (usually directories or specific linux packages)
                if branch == "master" and not is_dir and not any(item.lower().endswith(ext) for ext in [".appimage", ".deb"]):
                    continue
                    
                if not self.is_item_for_branch(item, branch):
                    continue

                short = self.get_short_version(item)
                matched = None
                for k in known_cloud_tags:
                    if branch == "master":
                        if k == short: matched = k; break
                    else: # Nightly
                        if short in k: matched = k; break
                
                if matched:
                    # Final Integrity Guard: Only mark as installed if executable exists
                    exe = self.find_executable(base_path, item)
                    if exe and os.path.exists(exe):
                        local_map[matched] = item
            return local_map
        except Exception as e:
            logger.error(f"Failed to scan local versions for {branch}: {e}")
            return {}
