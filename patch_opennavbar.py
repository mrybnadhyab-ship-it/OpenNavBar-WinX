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
# 1. Add WinX state + delayed check
# ============================================================

if "WINX_AUTO_SWITCH_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    state_code = """

    // WINX_AUTO_SWITCH_PATCH

    private var isWinXLauncher = false

    private val winXSwitchRunnable = Runnable {
        if (!isWinXLauncher) {
            showOverlay()
        }
    }

    // WINX_AUTO_SWITCH_PATCH_END

"""

    code = code[:match.end()] + state_code + code[match.end():]


# ============================================================
# 2. Find AccessibilityEvent handler
# ============================================================

if "WINX_AUTO_EVENT_PATCH" not in code:

    match = re.search(
        r"(fun\s+\w+\s*\([^)]*AccessibilityEvent[^)]*\)\s*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "AccessibilityEvent handler not found"
        )

    signature = match.group(1)

    param_match = re.search(
        r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:\s*AccessibilityEvent",
        signature
    )

    if not param_match:
        raise RuntimeError(
            "Could not determine AccessibilityEvent parameter"
        )

    event_var = param_match.group(1)

    patch = f"""

        // WINX_AUTO_EVENT_PATCH

        val winXCurrentPackage =
            {event_var}?.packageName?.toString() ?: ""

        if (winXCurrentPackage == "{WINX_PACKAGE}") {{

            isWinXLauncher = true

            // Cancel any pending re-show
            handler.removeCallbacks(winXSwitchRunnable)

            // Hide immediately
            hideOverlay()

        }} else {{

            // We have left Win X
            if (isWinXLauncher) {{

                isWinXLauncher = false

                // Small delay allows the new foreground window
                // to finish becoming active.
                handler.removeCallbacks(winXSwitchRunnable)
                handler.postDelayed(winXSwitchRunnable, 80L)
            }}
        }}

        // WINX_AUTO_EVENT_PATCH_END

"""

    code = code[:match.end()] + patch + code[match.end():]


# ============================================================
# 3. Protect showOverlay()
# ============================================================

def protect_function(name):

    global code

    pattern = re.compile(
        r"(fun\s+" + re.escape(name) +
        r"\s*\([^)]*\)\s*\{)"
    )

    match = pattern.search(code)

    if not match:
        print("Warning: function not found:", name)
        return

    start = match.end()

    section = code[start:start + 500]

    if "if (isWinXLauncher) return" not in section:

        code = (
            code[:start]
            + """

        if (isWinXLauncher) return

"""
            + code[start:]
        )


protect_function("showOverlay")
protect_function("showOverlayAnimated")


# ============================================================
# 4. Save
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("==============================================")
print("WinX AUTO HIDE / SHOW patch applied")
print("==============================================")
print("WinX package:", WINX_PACKAGE)
print("Hide: automatic")
print("Show: automatic after leaving WinX")
print("Delay: 80ms")
