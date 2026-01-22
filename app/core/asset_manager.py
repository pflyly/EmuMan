import sys
import platform

class AssetManager:
    """Handles GitHub release asset filtering and smart selection based on platform and user preference."""
    
    @staticmethod
    def is_file_for_platform(filename):
        """Standard filtering for OS and Architecture compatibility."""
        if not filename or not isinstance(filename, str):
            return False
            
        name = filename.lower()
        curr_arch = platform.machine().lower()
        curr_sys = platform.system()
        
        # Architecture Filter
        if "arm64" in curr_arch or "aarch64" in curr_arch:
            if any(x in name for x in ["x86_64", "amd64"]): return False
        else:
            if any(x in name for x in ["arm64", "aarch64"]): return False

        # System Filter
        if curr_sys == "Windows":
            if "windows" not in name: return False
            win_tags = ["msvc", "clang", "msys2", "mingw"]
            return any(x in name for x in win_tags)
        elif curr_sys == "Linux":
            if any(x in name for x in ["windows", "macos", "freebsd", "android"]): return False
            linux_exts = [".appimage", ".appbundle", ".deb", ".tar.gz", ".zip", ".7z"]
            return any(name.endswith(ext) for ext in linux_exts)
            
        return False

    @staticmethod
    def calculate_score(asset_name, pref_features):
        """Calculate a match score for an asset name based on user's previous preference and platform defaults."""
        name = asset_name.lower()
        score = 0
        
        # User Preference (from local installations)
        score += sum(15 for f in pref_features if f in name)
        
        # Essential Platform Weight
        curr_sys = sys.platform
        if curr_sys == "win32":
             if "windows" in name or "win64" in name: score += 50
        elif curr_sys == "linux":
             if "linux" in name: score += 50
             if "appimage" in name: score += 20
        
        # Architecture
        curr_arch = platform.machine().lower()
        if "arm64" in curr_arch or "aarch64" in curr_arch:
            if "arm64" in name or "aarch64" in name: score += 10
        else:
            if any(x in name for x in ["x86_64", "amd64", "x64"]): score += 10
        
        # Quality indicators
        if "standard" in name: score += 5
        if "generic" in name or "mingw" in name: score -= 2
        
        return score
