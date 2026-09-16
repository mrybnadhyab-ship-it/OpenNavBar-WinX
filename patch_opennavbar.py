import sys
import re

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    code = f.read()

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"

# 1. Add WinX state variable
if "private var isWinXLauncher" not in code:
    marker = "class NavigationOverlayService"
    pos = code.find(marker)

    if pos == -1:
        raise RuntimeError("NavigationOverlayService class not found")

    brace = code.find("{", pos)

    if brace == -1:
        raise RuntimeError("Class opening brace not found")

    code = (
        code[:brace + 1]
        + "\n\n    private var isWinXLauncher = false\n"
        + code[brace + 1:]
    )

# 2. Prevent overlay from appearing while WinX is active
for method in ["showOverlay()", "showOverlayAnimated()"]:
    pattern = r"(fun\s+" + re.escape(method[:-2]) + r"\s*\([^)]*\)\s*\{)"
    match = re.search(pattern, code)

    if match:
        start = match.end()
        section = code[start:start + 250]

        if "isWinXLauncher" not in section:
            code = (
                code[:start]
                + "\n        if (isWinXLauncher) return\n"
                + code[start:]
            )

# 3. Detect WinX from accessibility events
if "TYPE_WINDOW_STATE_CHANGED" in code:

    detection = '''
        val packageName = event.packageName?.toString() ?: ""

        val nowWinX = packageName == "''' + WINX_PACKAGE + '''"

        if (nowWinX != isWinXLauncher) {
            isWinXLauncher = nowWinX

            if (isWinXLauncher) {
                hideOverlay()
            } else {
                showOverlay()
            }
        }

'''

    # Insert once into onAccessibilityEvent
    event_pattern = r"(override\s+fun\s+onAccessibilityEvent\s*\(\s*event\s*:\s*AccessibilityEvent\s*\)\s*\{)"

    match = re.search(event_pattern, code)

    if not match:
        raise RuntimeError("onAccessibilityEvent not found")

    start = match.end()

    if "val nowWinX = packageName" not in code:
        code = code[:start] + "\n" + detection + code[start:]

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("WinX patch applied successfully.")
