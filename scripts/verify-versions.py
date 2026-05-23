#!/usr/bin/env python3
"""Verify version consistency across TaskPlanner codebase."""

import json
import sys
from pathlib import Path

def main():
    root = Path(__file__).parent.parent
    
    versions = {}
    issues = []
    
    # Check backend version
    tp_init = (root / "tp" / "__init__.py").read_text()
    for line in tp_init.split("\n"):
        if "__version__" in line and "=" in line:
            try:
                # Extract version from line like: __version__ = "0.1.27"
                version = line.split('"')[1] if '"' in line else line.split("'")[1]
                versions["backend (tp/__init__.py)"] = version
                break
            except IndexError:
                pass
    
    # Check frontend version
    frontend_json = json.loads((root / "frontend" / "package.json").read_text())
    versions["frontend (package.json)"] = frontend_json.get("version", "MISSING")
    
    # Check version.txt if it exists
    version_txt = root / "version.txt"
    if version_txt.exists():
        versions["version.txt (root)"] = version_txt.read_text().strip()
    
    # Print versions
    print("=" * 60)
    print("TaskPlanner Version Check")
    print("=" * 60)
    
    backend_ver = versions.get("backend (tp/__init__.py)")
    frontend_ver = versions.get("frontend (package.json)")
    
    for name, version in versions.items():
        status = "✓" if version != "MISSING" else "✗"
        print(f"{status} {name:40} {version}")
    
    # Validate
    print("\n" + "=" * 60)
    
    if not backend_ver or backend_ver == "MISSING":
        issues.append("Backend version not found in tp/__init__.py")
    
    if not frontend_ver or frontend_ver == "MISSING":
        issues.append("Frontend version not found in frontend/package.json")
    elif frontend_ver != backend_ver:
        issues.append(f"Version mismatch: backend={backend_ver}, frontend={frontend_ver}")
    
    if issues:
        print("⚠ ISSUES FOUND:")
        for issue in issues:
            print(f"  - {issue}")
        print("\nTo fix, ensure tp/__init__.py and frontend/package.json have matching versions.")
        return 1
    else:
        print("✓ All versions are in sync!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
