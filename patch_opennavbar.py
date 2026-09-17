import sys
import re
import os
import base64

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    code = f.read()

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"


def find_matching_brace(text, open_pos):
    depth = 0
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escape = False
    i = open_pos

    while i < len(text):
        c = text[i]
        n = text[i + 1] if i + 1 < len(text) else ""

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
        elif in_block_comment:
            if c == "*" and n == "/":
                in_block_comment = False
                i += 1
        elif in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
        elif in_char:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == "'":
                in_char = False
        else:
            if c == "/" and n == "/":
                in_line_comment = True
                i += 1
            elif c == "/" and n == "*":
                in_block_comment = True
                i += 1
            elif c == '"':
                in_string = True
            elif c == "'":
                in_char = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return i
        i += 1

    return -1


def find_function(text, name):
    m = re.search(
        rf"private\s+fun\s+{re.escape(name)}\s*\([^)]*\)\s*\{{",
        text,
    )
    if not m:
        return None

    open_pos = text.find("{", m.start(), m.end())
    if open_pos < 0:
        return None

    close_pos = find_matching_brace(text, open_pos)
    if close_pos < 0:
        return None

    return m, open_pos, close_pos


# ============================================================
# 1. IMPORTS
# ============================================================

required_imports = [
    "import android.graphics.Typeface",
    "import android.widget.TextView",
    "import java.text.SimpleDateFormat",
    "import java.util.Date",
    "import java.util.Locale",
]

anchor = "import android.accessibilityservice.AccessibilityService"
if anchor not in code:
    raise RuntimeError("AccessibilityService import not found")

for imp in required_imports:
    if imp not in code:
        code = code.replace(anchor, anchor + "\n" + imp, 1)


# ============================================================
# 2. WIN X STABLE PATCH
# ============================================================

if "WINX_STABLE_PATCH" not in code:
    match = re.search(r"(class\s+NavigationOverlayService[^{]*\{)", code)
    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    winx_patch = r'''

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

        view.animate().cancel()

        autoHideRunnable?.let {
            handler.removeCallbacks(it)
        }

        autoHideRunnable = null

        view.visibility = View.VISIBLE
        view.alpha = 1f
        view.translationX = 0f
        view.translationY = 0f

        isHidden = false
        isFullscreenHidden = false

        disableRevealZoneTouch()
    }

    // WINX_STABLE_PATCH_END
'''

    code = code[:match.end()] + winx_patch + code[match.end():]


# ============================================================
# 3. ACCESSIBILITY EVENT
# ============================================================

if "WINX_STABLE_EVENT_PATCH" not in code:
    match = re.search(
        r"(override\s+fun\s+onAccessibilityEvent\s*"
        r"\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{)",
        code,
    )
    if not match:
        raise RuntimeError("onAccessibilityEvent(AccessibilityEvent?) not found")

    event_patch = r'''
        // WINX_STABLE_EVENT_PATCH
        checkWinXStateDelayed()
        // WINX_STABLE_EVENT_PATCH_END

'''

    code = code[:match.end()] + event_patch + code[match.end():]


# ============================================================
# 4. PROTECT ONLY showOverlay()
#    Do NOT touch showOverlayAnimated() or showRevealZone().
# ============================================================

if "WINX_SHOW_OVERLAY_PROTECTION" not in code:
    match = re.search(
        r"(private\s+fun\s+showOverlay\s*\([^)]*\)\s*\{)",
        code,
    )
    if not match:
        raise RuntimeError("showOverlay() not found")

    protection = r'''
        // WINX_SHOW_OVERLAY_PROTECTION
        if (isWinXLauncher) return

'''
    code = code[:match.end()] + protection + code[match.end():]


# ============================================================
# 5. CLOCK + DATE
# ============================================================

if "WINX_CLOCK_DATE_PATCH" not in code:
    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code,
    )
    if not match:
        raise RuntimeError("NavigationOverlayService class not found")

    clock_patch = r'''

    // WINX_CLOCK_DATE_PATCH

    private var winXClockTextView: TextView? = null
    private var winXDateTextView: TextView? = null
    private var winXClockStarted = false

    private val winXClockRunnable = object : Runnable {
        override fun run() {
            try {
                val now = Date()

                val timeText = SimpleDateFormat(
                    "hh:mm a",
                    Locale.ENGLISH
                ).format(now)
                    .replace("AM", "ص")
                    .replace("PM", "م")

                val dateText = SimpleDateFormat(
                    "yyyy/MM/dd",
                    Locale.ENGLISH
                ).format(now)

                winXClockTextView?.text = timeText
                winXDateTextView?.text = dateText
            } catch (_: Exception) {
            }

            handler.postDelayed(this, 1000)
        }
    }

    private fun createWinXClock(
        textColor: Int,
        rotation: Float
    ): LinearLayout {

        val clockLayout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(0, 0, 0, 0)
            clipChildren = false
            clipToPadding = false
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val clock = TextView(this).apply {
            gravity = Gravity.CENTER
            isSingleLine = true
            includeFontPadding = false
            textSize = 9f
            typeface = Typeface.DEFAULT
            setTextColor(textColor)
            this.rotation = rotation
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val date = TextView(this).apply {
            gravity = Gravity.CENTER
            isSingleLine = true
            includeFontPadding = false
            textSize = 7f
            typeface = Typeface.DEFAULT
            setTextColor(textColor)
            this.rotation = rotation
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        clockLayout.addView(
            clock,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )

        clockLayout.addView(
            date,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )

        winXClockTextView = clock
        winXDateTextView = date

        if (!winXClockStarted) {
            winXClockStarted = true
            handler.removeCallbacks(winXClockRunnable)
            handler.post(winXClockRunnable)
        }

        return clockLayout
    }

    // WINX_CLOCK_DATE_PATCH_END
'''

    code = code[:match.end()] + clock_patch + code[match.end():]


# ============================================================
# 5.4. GMAIL APP BUTTON + CUSTOM ICON
# ============================================================

if "WINX_GMAIL_BUTTON_PATCH" not in code:
    # Resolve the cloned OpenNavBar app from the Kotlin source path.
    # The patch script itself is in the repository root, while the source
    # is inside opennavbar/app/... so searching from the script directory
    # can miss the real Android app.
    app_dir = None
    probe = os.path.abspath(os.path.dirname(path))
    while True:
        candidate_res = os.path.join(probe, "src", "main", "res")
        if os.path.isdir(candidate_res):
            app_dir = probe
            break
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent

    if app_dir is None:
        raise RuntimeError(
            "Android app res directory not found from NavigationOverlayService.kt path"
        )

    if app_dir is not None:
        drawable_dir = os.path.join(app_dir, "src", "main", "res", "drawable")
        os.makedirs(drawable_dir, exist_ok=True)
        gmail_icon_path = os.path.join(drawable_dir, "gmail_custom.png")
        if not os.path.exists(gmail_icon_path):
            try:
                icon_bytes = base64.b64decode(
                    """
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
zxrdjoaJfAWb7iVX7nA+TKU
