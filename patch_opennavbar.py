#!/usr/bin/env python3
import re
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")

if 'WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"' not in s:
    m = re.search(r'(class\s+NavigationOverlayService[^\{]*\{)', s)
    if not m:
        raise SystemExit("Could not locate NavigationOverlayService class.")
    insert = m.group(1) + '''
    private var isWinXLauncher = false
    private companion object {
        const val WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"
    }
'''
    s = s[:m.start()] + insert + s[m.end():]

if 'if (isWinXLauncher) return' not in s:
    m = re.search(r'((?:private|public|protected|internal)?\s*fun\s+showOverlayAnimated\s*\([^)]*\)\s*\{)', s)
    if m:
        s = s[:m.end()] + '\n        if (isWinXLauncher) return\n' + s[m.end():]

if 'event.packageName?.toString() == WINX_PACKAGE' not in s:
    pos = s.find('AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED')
    if pos == -1:
        raise SystemExit("Could not locate TYPE_WINDOW_STATE_CHANGED handling.")
    brace = s.find('{', pos)
    if brace == -1:
        raise SystemExit("Could not locate event block.")
    code = '''
            val foregroundPackage = event.packageName?.toString()
            val nowWinX = foregroundPackage == WINX_PACKAGE
            if (nowWinX != isWinXLauncher) {
                isWinXLauncher = nowWinX
                if (nowWinX) {
                    hideOverlay()
                } else {
                    showOverlayAnimated()
                }
            }
'''
    s = s[:brace + 1] + code + s[brace + 1:]

p.write_text(s, encoding="utf-8")
print("Patched:", p)
