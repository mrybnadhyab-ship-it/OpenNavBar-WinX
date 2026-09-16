import sys
import re

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    code = f.read()

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"

# ============================================================
# 1. Add WinX state
# ============================================================

if "WINX_PATCH_STATE" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "Could not find NavigationOverlayService class"
        )

    insert_pos = match.end()

    code = (
        code[:insert_pos]
        + """

    // WINX_PATCH_STATE
    private var isWinXLauncher = false
    // WINX_PATCH_STATE_END

"""
        + code[insert_pos:]
    )


# ============================================================
# 2. Find ANY function receiving AccessibilityEvent
# ============================================================

if "WINX_PATCH_EVENT" not in code:

    event_match = re.search(
        r"(fun\s+\w+\s*\([^)]*AccessibilityEvent[^)]*\)\s*\{)",
        code
    )

    if not event_match:

        # Try functions where event is typed indirectly
        event_match = re.search(
            r"(fun\s+\w+\s*\([^)]*\bevent\b[^)]*\)\s*\{)",
            code
        )

    if not event_match:
        raise RuntimeError(
            "Could not find Accessibility event handler"
        )

    insert_pos = event_match.end()

    patch = f"""

        // WINX_PATCH_EVENT
        val winXActive =
            event.packageName?.toString() == "{WINX_PACKAGE}"

        if (winXActive && !isWinXLauncher) {{
            isWinXLauncher = true
            hideOverlay()
        }} else if (!winXActive && isWinXLauncher) {{
            isWinXLauncher = false
            showOverlay()
        }}
        // WINX_PATCH_EVENT_END

"""

    code = code[:insert_pos] + patch + code[insert_pos:]


# ============================================================
# 3. Protect overlay showing
# ============================================================

# Patch function bodies only, NOT function declarations.

def protect_function(function_name):
    global code

    pattern = re.compile(
        r"(fun\s+" + re.escape(function_name) +
        r"\s*\([^)]*\)\s*\{)"
    )

    match = pattern.search(code)

    if not match:
        return

    body_start = match.end()

    check_area = code[body_start:body_start + 300]

    if "isWinXLauncher" not in check_area:

        code = (
            code[:body_start]
            + "\n        if (isWinXLauncher) return\n"
            + code[body_start:]
        )


protect_function("showOverlay")
protect_function("showOverlayAnimated")


# ============================================================
# 4. Save
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("======================================")
print("WinX patch applied successfully")
print("WinX package:", WINX_PACKAGE)
print("======================================")
