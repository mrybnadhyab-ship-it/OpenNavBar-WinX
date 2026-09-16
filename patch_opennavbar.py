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
# 1. Add WinX state + stable foreground check
# ============================================================

if "WINX_STABLE_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    insert = """

    // WINX_STABLE_PATCH

    private var isWinXLauncher = false

    private var winXCheckRunnable: Runnable? = null

    private fun getCurrentForegroundPackage(): String {
        return try {
            rootInActiveWindow?.packageName?.toString() ?: ""
        } catch (e: Exception) {
            ""
        }
    }

    private fun checkWinXStateDelayed() {

        winXCheckRunnable?.let {
            handler.removeCallbacks(it)
        }

        winXCheckRunnable = Runnable {

            val currentPackage = getCurrentForegroundPackage()

            if (currentPackage == "com.InternityLabs.Launcher.WinX") {

                // We are really inside Win X
                if (!isWinXLauncher) {

                    isWinXLauncher = true

                    navBarCheckRunnable?.let {
                        handler.removeCallbacks(it)
                    }

                    insetsDebounce?.let {
                        handler.removeCallbacks(it)
                    }

                    autoHideRunnable?.let {
                        handler.removeCallbacks(it)
                    }

                    hideOverlay()
                }

            } else {

                // Only restore if Win X was previously active.
                if (isWinXLauncher) {

                    isWinXLauncher = false

                    forceShowAfterWinX()
                }
            }
        }

        handler.postDelayed(winXCheckRunnable!!, 250)
    }

    private fun forceShowAfterWinX() {

        val view = overlayView ?: return

        // Cancel any running animation
        view.animate().cancel()

        // Cancel automatic hide
        autoHideRunnable?.let {
            handler.removeCallbacks(it)
        }

        autoHideRunnable = null

        // Restore overlay immediately
        view.visibility = View.VISIBLE
        view.alpha = 1f
        view.translationX = 0f
        view.translationY = 0f

        isHidden = false
        isFullscreenHidden = false

        disableRevealZoneTouch()
    }

    // WINX_STABLE_PATCH_END

"""

    code = code[:match.end()] + insert + code[match.end():]


# ============================================================
# 2. Patch AccessibilityEvent
# ============================================================

if "WINX_STABLE_EVENT_PATCH" not in code:

    match = re.search(
        r"(override\s+fun\s+onAccessibilityEvent\s*\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "onAccessibilityEvent(AccessibilityEvent?) not found"
        )

    patch = """

        // WINX_STABLE_EVENT_PATCH

        checkWinXStateDelayed()

        // WINX_STABLE_EVENT_PATCH_END

"""

    code = code[:match.end()] + patch + code[match.end():]


# ============================================================
# 3. Protect normal show functions
# ============================================================

def protect_function(name):

    global code

    pattern = re.compile(
        r"(fun\\s+" + re.escape(name) +
        r"\\s*\\([^)]*\\)\\s*\\{)"
    )

    match = pattern.search(code)

    if not match:
        print("Warning: function not found:", name)
        return

    start = match.end()
    section = code[start:start + 600]

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
print("WIN X STABLE HIDE / SHOW PATCH")
print("==============================================")
print("Win X package:", WINX_PACKAGE)
print("Detection: rootInActiveWindow")
print("Check delay: 250ms")
print("Inside Win X: HIDE")
print("Outside Win X: FORCE SHOW")
print("Transition events ignored")
print("==============================================")
