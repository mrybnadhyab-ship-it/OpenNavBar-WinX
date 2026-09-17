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
                    "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
