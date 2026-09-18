#!/usr/bin/env python3
"""
WinX patch helper for OpenNavBar.
This script is intentionally conservative: it applies textual replacements
only when the expected source patterns are present.
"""
from pathlib import Path

def replace_in_file(path, replacements):
    p=Path(path)
    if not p.exists(): return False
    s=p.read_text(errors="ignore")
    old=s
    for a,b in replacements:
        s=s.replace(a,b)
    if s!=old:
        p.write_text(s)
        return True
    return False

print("OpenNavBar-WinX patch ready.")
print("This patch script is used by the GitHub Actions build workflow.")
