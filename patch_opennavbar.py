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
# 1. Add WinX state + force-show function
# ============================================================

if "WINX_FORCE_SHOW_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    insert = """

    // WINX_FORCE_SHOW_PATCH

    private var isWinXLauncher = false

    private fun forceShowAfterWinX() {
        val view = overlayView ?: return

        // Cancel any hide animation that may still be running
        view.animate().cancel()

        // Cancel pending auto-hide
        autoHideRunnable?.let { handler.removeCallbacks(it) }
        autoHideRunnable = null

        // Immediately restore the overlay
        view.visibility = View.VISIBLE
        view.alpha = 1f
        view.translationX = 0f
        view.translationY = 0f

        isHidden = false
        isFullscreenHidden = false

        disableRevealZoneTouch()
    }

    // WINX_FORCE_SHOW_PATCH_END

"""

    code = code[:match.end()] + insert + code[match.end():]


# ============================================================
# 2. Patch AccessibilityEvent handler
# ============================================================

if "WINX_FORCE_EVENT_PATCH" not in code:

    match = re.search(
        r"(override\s+fun\s+onAccessibilityEvent\s*\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "onAccessibilityEvent(AccessibilityEvent?) not found"
        )

    patch = f"""

        // WINX_FORCE_EVENT_PATCH

        val winXPackage =
            event?.packageName?.toString() ?: ""

        if (winXPackage == "{WINX_PACKAGE}") {{

            if (!isWinXLauncher) {{
                isWinXLauncher = true

                // Cancel anything that could restore the bar
                navBarCheckRunnable?.let {{ handler.removeCallbacks(it) }}
                insetsDebounce?.let {{ handler.removeCallbacks(it) }}
                autoHideRunnable?.let {{ handler.removeCallbacks(it) }}

                hideOverlay()
            }}

        }} else {{

            if (isWinXLauncher) {{
                isWinXLauncher = false

                // Force the overlay back immediately.
                // Do NOT use showOverlayAnimated(), because
                // isHidden may still be false while hide animation
                // is finishing.
                forceShowAfterWinX()
            }}
        }}

        // WINX_FORCE_EVENT_PATCH_END

"""

    code = code[:match.end()] + patch + code[match.end():]


# ============================================================
# 3. Prevent normal show functions from showing over Win X
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
print("WIN X FORCE HIDE / SHOW PATCH APPLIED")
print("==============================================")
print("Win X package:", WINX_PACKAGE)
print("Inside Win X: HIDE")
print("Outside Win X: FORCE SHOW")
print("Animation race: FIXED")
print("Nullable Runnable errors: FIXED")
print("==============================================")
