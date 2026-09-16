import sys
import re

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    code = f.read()

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"

# --------------------------------------------------
# 1. Add WinX state
# --------------------------------------------------

if "WINX_PATCH_STATE" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    code = (
        code[:match.end()]
        + """

    // WINX_PATCH_STATE
    private var isWinXLauncher = false
    // WINX_PATCH_STATE_END

"""
        + code[match.end():]
    )

# --------------------------------------------------
# 2. Find AccessibilityEvent handler
# --------------------------------------------------

if "WINX_PATCH_EVENT" not in code:

    match = re.search(
        r"(fun\s+\w+\s*\([^)]*AccessibilityEvent[^)]*\)\s*\{)",
        code
    )

    if not match:
        raise RuntimeError("AccessibilityEvent handler not found")

    # Get the actual parameter name
    signature = match.group(1)

    param_match = re.search(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:\s*AccessibilityEvent",
        signature
    )

    if not param_match:
        raise RuntimeError("Could not determine AccessibilityEvent parameter")

    event_var = param_match.group(1)

    patch = f"""

        // WINX_PATCH_EVENT
        val winXActive =
            {event_var}?.packageName?.toString() == "{WINX_PACKAGE}"

        if (winXActive && !isWinXLauncher) {{
            isWinXLauncher = true
            hideOverlay()
        }} else if (!winXActive && isWinXLauncher) {{
            isWinXLauncher = false
            showOverlay()
        }}
        // WINX_PATCH_EVENT_END

"""

    code = code[:match.end()] + patch + code[match.end():]

# --------------------------------------------------
# 3. Protect showOverlay
# --------------------------------------------------

def protect_function(name):
    global code

    pattern = re.compile(
        r"(fun\s+" + re.escape(name) +
        r"\s*\([^)]*\)\s*\{)"
    )

    match = pattern.search(code)

    if not match:
        return

    start = match.end()
    area = code[start:start + 300]

    if "if (isWinXLauncher) return" not in area:
        code = (
            code[:start]
            + "\n        if (isWinXLauncher) return\n"
            + code[start:]
        )

protect_function("showOverlay")
protect_function("showOverlayAnimated")

# --------------------------------------------------
# 4. Save
# --------------------------------------------------

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("======================================")
print("WinX patch applied successfully")
print("AccessibilityEvent nullable fix applied")
print("======================================")
