case(Locale.getDefault()) ?: ""
                    val isStart = text == "start" || desc == "start" || id.contains("start")

                    if (isStart) {
                        if (node.isClickable && node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
                        var parent = node.parent
                        while (parent != null) {
                            if (parent.isClickable && parent.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return true
                            parent = parent.parent
                        }
                    }

                    for (i in 0 until node.childCount) {
                        try { node.getChild(i)?.let { queue.add(it) } } catch (_: Exception) { }
                    }
                } catch (_: Exception) { }
            }
        } catch (_: Exception) { }
        return false
    }

    private fun openWinXStart() {
        try {
            if (!isWinXLauncher) {
                val intent = packageManager.getLaunchIntentForPackage(WINX_PACKAGE_PATCH_CONSTANT)
                if (intent != null) {
                    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
                    startActivity(intent)
                }
                handler.postDelayed({
                    try {
                        updateWinXState(WINX_PACKAGE_PATCH_CONSTANT)
                        clickWinXStartButton()
                    } catch (_: Exception) { }
                }, 650)
            } else if (!clickWinXStartButton()) {
                handler.postDelayed({
                    try { clickWinXStartButton() } catch (_: Exception) { }
                }, 250)
            }
        } catch (_: Exception) { }
    }

"""
    code = code[:pos] + helpers + code[pos:]

# ------------------------------------------------------------
# Preserve original onAccessibilityEvent; only inject detection
# ------------------------------------------------------------
result = find_function(code, "override fun onAccessibilityEvent(event: AccessibilityEvent?)")
if not result:
    fail("onAccessibilityEvent not found")
start, brace, end = result
old = code[start:end + 1]
if "WINX_EVENT_PATCH" not in old:
    inject = """
        // ====================================================
        // WINX_EVENT_PATCH
        // ====================================================
        try {
            val eventPackage = event?.packageName?.toString()
            if (!eventPackage.isNullOrEmpty()) {
                updateWinXState(eventPackage)
            } else {
                checkWinXStateDelayed()
            }
        } catch (_: Exception) {
        }

"""
    new = old.replace("{", "{\n" + inject, 1)
    code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# Any temporary hide is allowed only in WinX
# ------------------------------------------------------------
result = find_function(code, "private fun scheduleTemporaryHide")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_TEMP_HIDE_PROTECTION" not in old:
        new = old.replace("{", "{\n        // WINX_TEMP_HIDE_PROTECTION\n        if (!isWinXLauncher) return", 1)
        code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# Auto hide only in WinX
# ------------------------------------------------------------
result = find_function(code, "private fun scheduleAutoHide")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_AUTO_HIDE_PROTECTION" not in old:
        new = old.replace("{", "{\n        // WINX_AUTO_HIDE_PROTECTION\n        if (!isWinXLauncher) return", 1)
        code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# Long press Home opens WinX Start only while WinX is active
# ------------------------------------------------------------
result = find_function(code, "private fun handleLongPress")
if not result:
    fail("handleLongPress not found")
start, brace, end = result
old = code[start:end + 1]
if "WINX_LONG_PRESS_START" not in old:
    new = """private fun handleLongPress(buttonType: String) {
        // ====================================================
        // WINX_LONG_PRESS_START
        // ====================================================
        if (isButtonDisabled(buttonType)) return
        if (isButtonHidden(buttonType)) return
        if (!prefs.getBoolean("enable_long_press", true)) return

        if (buttonType == "home" && isWinXLauncher) {
            openWinXStart()
            return
        }

        executeAction("long_press_$buttonType", 70)
    }"""
    code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# Clock/date: one line to avoid malformed Kotlin string literals
# ------------------------------------------------------------
result = find_function(code, "private fun configureOverlayView")
if not result:
    fail("configureOverlayView not found")
fn_start, fn_brace, fn_end = result
configure_code = code[fn_start:fn_end + 1]

if "WINX_CLOCK_INSERTED" not in configure_code:
    add_match = re.search(r"container\.addView\(frame\)", configure_code)
    if not add_match:
        fail("Could not find container.addView(frame)")

    fn_open = fn_brace - fn_start
    abs_add_end = fn_open + 1 + add_match.end()
    tail = configure_code[abs_add_end:]
    loop_close_rel = tail.find("}")
    if loop_close_rel < 0:
        fail("Could not find button loop closing brace")
    insert_pos = abs_add_end + loop_close_rel + 1

    clock_block = """
        // ====================================================
        // WINX_CLOCK_INSERTED
        // ====================================================
        try {
            winXClockView?.let {
                try { container.removeView(it) } catch (_: Exception) { }
            }

            winXClockView = TextView(this).apply {
                textSize = 9f
                setTypeface(Typeface.DEFAULT, Typeface.NORMAL)
                gravity = Gravity.CENTER
                setSingleLine(true)
                includeFontPadding = false
                setTextColor(Color.WHITE)
                isClickable = false
                isFocusable = false
            }

            winXClockHandler?.removeCallbacksAndMessages(null)
            winXClockHandler = Handler(Looper.getMainLooper())

            winXClockRunnable = object : Runnable {
                override fun run() {
                    try {
                        val now = Date()
                        val timeFormat = SimpleDateFormat("HH:mm", Locale.getDefault())
                        val dateFormat = SimpleDateFormat("dd/MM", Locale.getDefault())
                        winXClockView?.text = timeFormat.format(now) + "  " + dateFormat.format(now)
                    } catch (_: Exception) { }

                    try {
                        winXClockHandler?.postDelayed(this, 1000)
                    } catch (_: Exception) { }
                }
            }

            val clockParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.MATCH_PARENT
            )
            clockParams.gravity = Gravity.CENTER_VERTICAL
            clockParams.leftMargin = 4
            clockParams.rightMargin = 4

            val clock = winXClockView
            if (clock != null) {
                if (prefs.getBoolean("swap_back_recent", false)) {
                    container.addView(clock, 1, clockParams)
                } else {
                    container.addView(clock, 3, clockParams)
                }
                winXClockRunnable?.let { winXClockHandler?.post(it) }
            }
        } catch (_: Exception) { }

"""

    code = code[:fn_start] + configure_code[:insert_pos] + clock_block + configure_code[insert_pos:] + code[fn_end + 1:]

# ------------------------------------------------------------
# Clock cleanup
# ------------------------------------------------------------
result = find_function(code, "override fun onDestroy")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_CLOCK_CLEANUP" not in old:
        cleanup = """
        // WINX_CLOCK_CLEANUP
        try {
            winXClockHandler?.removeCallbacksAndMessages(null)
            winXClockHandler = null
            winXClockRunnable = null
            winXClockView = null
        } catch (_: Exception) { }

"""
        new = old.replace("{", "{\n" + cleanup, 1)
        code = code[:start] + new + code[end + 1:]

# ------------------------------------------------------------
# State checks
# ------------------------------------------------------------
result = find_function(code, "override fun onServiceConnected")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_SERVICE_CONNECTED" not in old:
        new = old.replace("{", "{\n        // WINX_SERVICE_CONNECTED\n        checkWinXStateDelayed()", 1)
        code = code[:start] + new + code[end + 1:]

result = find_function(code, "override fun onSharedPreferenceChanged")
if result:
    start, brace, end = result
    old = code[start:end + 1]
    if "WINX_PREF_STATE_CHECK" not in old:
        new = old.replace("{", "{\n        // WINX_PREF_STATE_CHECK\n        checkWinXStateDelayed()", 1)
        code = code[:start] + new + code[end + 1:]

SOURCE.write_text(code, encoding="utf-8")
print("==============================================")
print(" OpenNavBar-WinX PATCH COMPLETE")
print("==============================================")
print("Source:", SOURCE)
print("WinX detection: OK")
print("WinX-only auto hide: OK")
print("MiXplorer stability: OK")
print("Long press Home -> WinX Start: OK")
print("Clock/date: OK")
print("==============================================")
import sys
import re

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
        rf"private\s+fun\s+{re.escape(name)}\s*\([^)]*\)\s*\{",
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
    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

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
        raise RuntimeError(
            "onAccessibilityEvent(AccessibilityEvent?) not found"
        )

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
            this.rotation = rotation
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
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val date = TextView(this).apply {
            gravity = Gravity.CENTER
            isSingleLine = true
            includeFontPadding = false
            textSize = 9f
            typeface = Typeface.DEFAULT
            setTextColor(textColor)
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

        val dateParams = LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).apply {
            topMargin = dpToPx(1)
        }

        clockLayout.addView(date, dateParams)

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
# 6. INSERT CLOCK WITHOUT REPLACING THE ORIGINAL BUTTON LAYOUT
#    This keeps all original SwipeInterceptLayout code untouched.
# ============================================================

if "WINX_CLOCK_LAYOUT_PATCH" not in code:
    fn = find_function(code, "configureOverlayView")

    if not fn:
        raise RuntimeError("configureOverlayView() not found")

    _, fn_open, fn_close = fn
    body = code[fn_open + 1:fn_close]

    add_match = re.search(
        r"container\.addView\s*\(\s*frame\s*\)",
        body
    )

    if not add_match:
        raise RuntimeError(
            "Original navigation button addView(frame) not found"
        )

    abs_add_end = fn_open + 1 + add_match.end()
    tail = code[abs_add_end:fn_close]

    loop_close_rel = tail.find("}")

    if loop_close_rel < 0:
        raise RuntimeError(
            "Navigation button loop end not found"
        )

    insert_pos = abs_add_end + loop_close_rel + 1

    clock_layout_patch = r'''

        // WINX_CLOCK_LAYOUT_PATCH

        val winXClockRotation = when (position) {
            "left" -> 90f
            "right" -> -90f
            else -> 0f
        }

        val winXClockView = createWinXClock(
            buttonColor,
            winXClockRotation
        ).apply {
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val winXSpacer = View(this).apply {
            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val winXClockParams = if (isVerticalBar) {
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                hitboxSize,
                0f
            )
        } else {
            LinearLayout.LayoutParams(
                dpToPx(50),
                LinearLayout.LayoutParams.MATCH_PARENT,
                0f
            )
        }

        val winXSpacerParams = if (isVerticalBar) {
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1f
            )
        } else {
            LinearLayout.LayoutParams(
                0,
                LinearLayout.LayoutParams.MATCH_PARENT,
                1f
            )
        }

        if (shouldSwap) {
            // Recent | Clock | SPACE | Home | Back
            container.addView(winXClockView, 1, winXClockParams)
            container.addView(winXSpacer, 2, winXSpacerParams)
        } else {
            // Back | Home | SPACE | Clock | Recent
            container.addView(winXSpacer, 2, winXSpacerParams)
            container.addView(winXClockView, 3, winXClockParams)
        }

        // WINX_CLOCK_LAYOUT_PATCH_END
'''

    code = code[:insert_pos] + clock_layout_patch + code[insert_pos:]


# ============================================================
# 7. CONTAINER GRAVITY
# ============================================================

if "WINX_CLOCK_GRAVITY_PATCH" not in code:
    old = "container.gravity = Gravity.CENTER"

    new = r'''container.gravity =
        if (isVerticalBar)
            Gravity.CENTER_HORIZONTAL
        else
            Gravity.CENTER_VERTICAL

        // WINX_CLOCK_GRAVITY_PATCH'''

    if old in code:
        code = code.replace(old, new, 1)
    else:
        print(
            "Warning: container.gravity line not found; "
            "leaving original gravity"
        )


# ============================================================
# 8. CLOCK CLEANUP
# ============================================================

if "WINX_CLOCK_CLEANUP_PATCH" not in code:
    match = re.search(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)",
        code,
    )

    if match:
        cleanup = r'''
        // WINX_CLOCK_CLEANUP_PATCH
        handler.removeCallbacks(winXClockRunnable)
        winXClockStarted = false
        winXClockTextView = null
        winXDateTextView = null

'''

        code = code[:match.end()] + cleanup + code[match.end():]


# ============================================================
# 9. FIX OCCASIONAL DISAPPEARANCE ONLY
# ============================================================

if "WINX_AUTO_HIDE_GUARD_PATCH" not in code:
    fn = find_function(code, "scheduleAutoHide")

    if fn:
        _, fn_open, fn_close = fn

        guard = r'''
        // WINX_AUTO_HIDE_GUARD_PATCH
        if (!isWinXLauncher) return

'''

        code = (
            code[:fn_open + 1]
            + guard
            + code[fn_open + 1:]
        )
    else:
        print(
            "Warning: scheduleAutoHide() not found; "
            "no auto-hide guard added"
        )


# ============================================================
# 10. SAVE
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("================================================")
print(" OPENNAVBAR WIN X + CLOCK PATCH")
print("================================================")
print("")
print("Win X package:")
print(WINX_PACKAGE)
print("")
print("Win X: hide only on Win X launcher")
print("Clock: 9sp time / 9sp date / group rotation / 1dp gap / non-touch")
print("Swipe: ORIGINAL SWIPE/REVEAL CODE PRESERVED")
print("Fix: original auto-hide disabled outside Win X")
print("================================================")
print("PATCH COMPLETE")
print("================================================")
