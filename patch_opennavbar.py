#!/usr/bin/env python3

import re
import sys
from pathlib import Path


if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: patch_opennavbar.py <NavigationOverlayService.kt>"
    )


p = Path(sys.argv[1])

if not p.exists():
    raise SystemExit(f"File not found: {p}")


s = p.read_text(encoding="utf-8")


WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"


# ---------------------------------------------------------
# 1. Add WINX_PACKAGE outside the class.
#    This avoids creating a second companion object.
# ---------------------------------------------------------

if 'private const val WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"' not in s:

    class_match = re.search(
        r'class\s+NavigationOverlayService[^\{]*\{',
        s
    )

    if not class_match:
        raise SystemExit(
            "Could not locate NavigationOverlayService class."
        )

    constant = (
        'private const val WINX_PACKAGE = '
        '"com.InternityLabs.Launcher.WinX"\n\n'
    )

    s = (
        s[:class_match.start()]
        + constant
        + s[class_match.start():]
    )


# ---------------------------------------------------------
# 2. Add WinX state variable inside NavigationOverlayService.
# ---------------------------------------------------------

if 'private var isWinXLauncher = false' not in s:

    class_match = re.search(
        r'(class\s+NavigationOverlayService[^\{]*\{)',
        s
    )

    if not class_match:
        raise SystemExit(
            "Could not locate NavigationOverlayService class."
        )

    s = (
        s[:class_match.end()]
        + '\n\n    private var isWinXLauncher = false\n'
        + s[class_match.end():]
    )


# ---------------------------------------------------------
# 3. Prevent the overlay from appearing while WinX
#    is the foreground application.
# ---------------------------------------------------------

if 'if (isWinXLauncher) return' not in s:

    show_match = re.search(
        r'((?:private|public|protected|internal)?\s*'
        r'fun\s+showOverlayAnimated\s*'
        r'\([^)]*\)\s*\{)',
        s
    )

    if show_match:

        s = (
            s[:show_match.end()]
            + '\n        if (isWinXLauncher) return\n'
            + s[show_match.end():]
        )


# ---------------------------------------------------------
# 4. Detect WinX from AccessibilityEvent.
# ---------------------------------------------------------

if 'val nowWinX = foregroundPackage == WINX_PACKAGE' not in s:

    pos = s.find(
        'AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED'
    )

    if pos == -1:
        raise SystemExit(
            "Could not locate TYPE_WINDOW_STATE_CHANGED handling."
        )

    brace = s.find('{', pos)

    if brace == -1:
        raise SystemExit(
            "Could not locate event block."
        )

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

    s = (
        s[:brace + 1]
        + code
        + s[brace + 1:]
    )


# ---------------------------------------------------------
# 5. Save patched file.
# ---------------------------------------------------------

p.write_text(s, encoding="utf-8")

print("Patched:", p)
