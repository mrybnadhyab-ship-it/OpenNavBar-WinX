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
    "import android.view.KeyEvent",
    "import java.text.SimpleDateFormat",
    "import java.util.Date",
    "import java.util.Locale",
]

anchor = "import android.accessibilityservice.AccessibilityService"

if anchor not in code:
    raise RuntimeError(
        "AccessibilityService import not found"
    )

for imp in required_imports:
    if imp not in code:
        code = code.replace(
            anchor,
            anchor + "\n" + imp,
            1
        )


# ============================================================
# 2. WIN X STABLE PATCH
# ============================================================

if "WINX_STABLE_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

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

            val currentPackage =
                getCurrentForegroundPackage()

            if (
                currentPackage ==
                "com.InternityLabs.Launcher.WinX"
            ) {

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

        handler.postDelayed(
            winXCheckRunnable!!,
            250
        )
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

    code = (
        code[:match.end()]
        + winx_patch
        + code[match.end():]
    )


# ============================================================
# 3. ACCESSIBILITY EVENT
# ============================================================

if "WINX_STABLE_EVENT_PATCH" not in code:

    match = re.search(
        r"(override\s+fun\s+onAccessibilityEvent\s*"
        r"\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{)",
        code
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

    code = (
        code[:match.end()]
        + event_patch
        + code[match.end():]
    )


# ============================================================
# 4. PROTECT ONLY showOverlay()
# ============================================================

if "WINX_SHOW_OVERLAY_PROTECTION" not in code:

    match = re.search(
        r"(private\s+fun\s+showOverlay\s*\([^)]*\)\s*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "showOverlay() not found"
        )

    protection = r'''
        // WINX_SHOW_OVERLAY_PROTECTION

        if (isWinXLauncher) return

'''

    code = (
        code[:match.end()]
        + protection
        + code[match.end():]
    )


# ============================================================
# 5. PORTRAIT FULLSCREEN FIX
# ============================================================

if "WINX_PORTRAIT_FULLSCREEN_FIX" not in code:

    old = (
        'if (prefs.getBoolean("hide_on_fullscreen", true))'
    )

    new = '''if (
                    prefs.getBoolean("hide_on_fullscreen", true) &&
                    resources.configuration.orientation !=
                        android.content.res.Configuration.ORIENTATION_PORTRAIT
                )'''

    if old in code:

        code = code.replace(
            old,
            new,
            1
        )

    else:

        print(
            "Warning: fullscreen condition not found; "
            "portrait fullscreen fix was not inserted"
        )

    marker = r'''

    // WINX_PORTRAIT_FULLSCREEN_FIX
    // Portrait orientation keeps OpenNavBar visible.
    // Landscape keeps the original fullscreen behavior.

'''

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    code = (
        code[:match.end()]
        + marker
        + code[match.end():]
    )


# ============================================================
# 6. CLOCK + DATE
# ============================================================

if "WINX_CLOCK_DATE_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    clock_patch = r'''

    // WINX_CLOCK_DATE_PATCH

    private var winXClockTextView: TextView? = null
    private var winXDateTextView: TextView? = null
    private var winXClockStarted = false

    private val winXClockRunnable =
        object : Runnable {

        override fun run() {

            try {

                val now = Date()

                val timeText =
                    SimpleDateFormat(
                        "hh:mm a",
                        Locale.ENGLISH
                    )
                    .format(now)
                    .replace("AM", "ص")
                    .replace("PM", "م")

                val dateText =
                    SimpleDateFormat(
                        "yyyy/MM/dd",
                        Locale.ENGLISH
                    )
                    .format(now)

                winXClockTextView?.text =
                    timeText

                winXDateTextView?.text =
                    dateText

            } catch (_: Exception) {
            }

            handler.postDelayed(
                this,
                1000
            )
        }
    }

    private fun createWinXClock(
        textColor: Int,
        rotation: Float
    ): LinearLayout {

        val clockLayout =
            LinearLayout(this).apply {

            orientation =
                LinearLayout.VERTICAL

            gravity =
                Gravity.CENTER

            setPadding(
                0,
                0,
                0,
                0
            )

            this.rotation =
                rotation

            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val clock =
            TextView(this).apply {

            gravity =
                Gravity.CENTER

            isSingleLine = true

            includeFontPadding =
                false

            textSize = 9f

            typeface =
                Typeface.DEFAULT

            setTextColor(
                textColor
            )

            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val date =
            TextView(this).apply {

            gravity =
                Gravity.CENTER

            isSingleLine = true

            includeFontPadding =
                false

            textSize = 9f

            typeface =
                Typeface.DEFAULT

            setTextColor(
                textColor
            )

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

        val dateParams =
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {

            topMargin =
                dpToPx(1)
        }

        clockLayout.addView(
            date,
            dateParams
        )

        winXClockTextView =
            clock

        winXDateTextView =
            date

        if (!winXClockStarted) {

            winXClockStarted =
                true

            handler.removeCallbacks(
                winXClockRunnable
            )

            handler.post(
                winXClockRunnable
            )
        }

        return clockLayout
    }

    // WINX_CLOCK_DATE_PATCH_END
'''

    code = (
        code[:match.end()]
        + clock_patch
        + code[match.end():]
    )


# ============================================================
# 7. INSERT CLOCK
# ============================================================

if "WINX_CLOCK_LAYOUT_PATCH" not in code:

    fn = find_function(
        code,
        "configureOverlayView"
    )

    if not fn:
        raise RuntimeError(
            "configureOverlayView() not found"
        )

    _, fn_open, fn_close = fn

    body = code[
        fn_open + 1:
        fn_close
    ]

    add_match = re.search(
        r"container\.addView\s*\(\s*frame\s*\)",
        body
    )

    if not add_match:
        raise RuntimeError(
            "Original navigation button addView(frame) not found"
        )

    abs_add_end =
        fn_open + 1 + add_match.end()

    tail =
        code[abs_add_end:fn_close]

    loop_close_rel =
        tail.find("}")

    if loop_close_rel < 0:
        raise RuntimeError(
            "Navigation button loop end not found"
        )

    insert_pos =
        abs_add_end + loop_close_rel + 1

    clock_layout_patch = r'''

        // WINX_CLOCK_LAYOUT_PATCH

        val winXClockRotation =
            when (position) {

                "left" -> 90f

                "right" -> -90f

                else -> 0f
            }

        val winXClockView =
            createWinXClock(
                buttonColor,
                winXClockRotation
            ).apply {

            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val winXSpacer =
            View(this).apply {

            isClickable = false
            isFocusable = false
            isFocusableInTouchMode = false
            isLongClickable = false
        }

        val winXClockParams =
            if (isVerticalBar) {

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

        val winXSpacerParams =
            if (isVerticalBar) {

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

            container.addView(
                winXClockView,
                1,
                winXClockParams
            )

            container.addView(
                winXSpacer,
                2,
                winXSpacerParams
            )

        } else {

            // Back | Home | SPACE | Clock | Recent

            container.addView(
                winXSpacer,
                2,
                winXSpacerParams
            )

            container.addView(
                winXClockView,
                3,
                winXClockParams
            )
        }

        // WINX_CLOCK_LAYOUT_PATCH_END
'''

    code = (
        code[:insert_pos]
        + clock_layout_patch
        + code[insert_pos:]
    )


# ============================================================
# 8. CONTAINER GRAVITY
# ============================================================

if "WINX_CLOCK_GRAVITY_PATCH" not in code:

    old = (
        "container.gravity = Gravity.CENTER"
    )

    new = r'''container.gravity =
        if (isVerticalBar)
            Gravity.CENTER_HORIZONTAL
        else
            Gravity.CENTER_VERTICAL

        // WINX_CLOCK_GRAVITY_PATCH'''

    if old in code:

        code = code.replace(
            old,
            new,
            1
        )

    else:

        print(
            "Warning: container.gravity line not found; "
            "leaving original gravity"
        )


# ============================================================
# 9. CLOCK CLEANUP
# ============================================================

if "WINX_CLOCK_CLEANUP_PATCH" not in code:

    match = re.search(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)",
        code
    )

    if match:

        cleanup = r'''
        // WINX_CLOCK_CLEANUP_PATCH

        handler.removeCallbacks(
            winXClockRunnable
        )

        winXClockStarted = false

        winXClockTextView = null

        winXDateTextView = null

'''

        code = (
            code[:match.end()]
            + cleanup
            + code[match.end():]
        )


# ============================================================
# 10. LONG PRESS BACK -> WIN X
# ============================================================

if "WINX_LONG_BACK_START_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    long_back_patch = r'''

    // WINX_LONG_BACK_START_PATCH

    private var winXBackLongPressed = false
    private var winXBackDown = false

    private val winXBackLongPressRunnable =
        Runnable {

        if (winXBackDown) {

            winXBackLongPressed =
                true

            try {

                val launchIntent =
                    packageManager
                        .getLaunchIntentForPackage(
                            "com.InternityLabs.Launcher.WinX"
                        )

                if (launchIntent != null) {

                    launchIntent.addFlags(
                        Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_CLEAR_TOP
                    )

                    startActivity(
                        launchIntent
                    )
                }

            } catch (_: Exception) {
            }
        }
    }

    private fun handleWinXBackKey(
        event: KeyEvent
    ): Boolean {

        if (
            event.keyCode !=
            KeyEvent.KEYCODE_BACK
        ) {
            return false
        }

        when (event.action) {

            KeyEvent.ACTION_DOWN -> {

                if (!winXBackDown) {

                    winXBackDown = true

                    winXBackLongPressed =
                        false

                    handler.removeCallbacks(
                        winXBackLongPressRunnable
                    )

                    handler.postDelayed(
                        winXBackLongPressRunnable,
                        550L
                    )
                }

                return true
            }

            KeyEvent.ACTION_UP -> {

                handler.removeCallbacks(
                    winXBackLongPressRunnable
                )

                val wasLongPressed =
                    winXBackLongPressed

                winXBackDown = false

                winXBackLongPressed =
                    false

                if (!wasLongPressed) {

                    performGlobalAction(
                        AccessibilityService
                            .GLOBAL_ACTION_BACK
                    )
                }

                return true
            }
        }

        return true
    }

    // WINX_LONG_BACK_START_PATCH_END
'''

    code = (
        code[:match.end()]
        + long_back_patch
        + code[match.end():]
    )


# ============================================================
# 11. ON KEY EVENT
# ============================================================

if "WINX_LONG_BACK_ON_KEY_EVENT" not in code:

    key_match = re.search(
        r"(override\s+fun\s+onKeyEvent\s*\(\s*"
        r"event\s*:\s*KeyEvent\s*\)\s*:\s*Boolean\s*\{)",
        code
    )

    if key_match:

        key_event_patch = r'''
        // WINX_LONG_BACK_ON_KEY_EVENT

        if (
            event.keyCode ==
            KeyEvent.KEYCODE_BACK
        ) {

            return handleWinXBackKey(
                event
            )
        }

'''

        code = (
            code[:key_match.end()]
            + key_event_patch
            + code[key_match.end():]
        )

    else:

        insert_at =
            code.rfind("\n}")

        if insert_at < 0:
            raise RuntimeError(
                "Could not find final class brace"
            )

        key_event_method = r'''

    // WINX_LONG_BACK_ON_KEY_EVENT

    override fun onKeyEvent(
        event: KeyEvent
    ): Boolean {

        if (
            event.keyCode ==
            KeyEvent.KEYCODE_BACK
        ) {

            return handleWinXBackKey(
                event
            )
        }

        return super.onKeyEvent(
            event
        )
    }

    // WINX_LONG_BACK_ON_KEY_EVENT_END
'''

        code = (
            code[:insert_at]
            + key_event_method
            + code[insert_at:]
        )


# ============================================================
# 12. LONG PRESS CLEANUP
# ============================================================

if "WINX_LONG_BACK_CLEANUP_PATCH" not in code:

    destroy_match = re.search(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)",
        code
    )

    if destroy_match:

        cleanup = r'''
        // WINX_LONG_BACK_CLEANUP_PATCH

        handler.removeCallbacks(
            winXBackLongPressRunnable
        )

        winXBackDown = false

        winXBackLongPressed = false

'''

        code = (
            code[:destroy_match.end()]
            + cleanup
            + code[destroy_match.end():]
        )


# ============================================================
# 13. SAVE
# ============================================================

with open(
    path,
    "w",
    encoding="utf-8"
) as f:

    f.write(code)


print("================================================")
print(" OPENNAVBAR WIN X 9F FIX")
print("================================================")
print("")
print("Win X package:")
print(WINX_PACKAGE)
print("")
print("Win X: hide only on Win X launcher")
print("Portrait fullscreen: FIXED / ALWAYS VISIBLE")
print("Landscape fullscreen: ORIGINAL BEHAVIOR")
print("")
print("Clock: 9sp time")
print("Date: 9sp")
print("Clock gap: 1dp")
print("Clock: non-touch")
print("")
print("Long Back: 550ms -> Win X Launcher")
print("Normal Back: GLOBAL_ACTION_BACK")
print("")
print("Original Swipe/Reveal: PRESERVED")
print("================================================")
print("PATCH COMPLETE")
print("================================================")
