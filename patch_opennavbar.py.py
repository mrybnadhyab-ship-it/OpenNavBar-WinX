import sys
import re
import os

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
            # The icon is kept as a normal repository file, not embedded in Python.
            # This avoids huge Base64 strings and Python syntax errors.
            repo_root = os.path.abspath(os.getcwd())
            source_icon = os.path.join(repo_root, "gmail_custom.png")

            if not os.path.exists(source_icon):
                # Also try the directory containing the patch script.
                source_icon = os.path.join(
                    os.path.abspath(os.path.dirname(__file__)),
                    "gmail_custom.png"
                )

            if not os.path.exists(source_icon):
                raise RuntimeError(
                    "gmail_custom.png not found. Put gmail_custom.png in the repository root."
                )

            try:
                with open(source_icon, "rb") as src, open(gmail_icon_path, "wb") as dst:
                    dst.write(src.read())
            except Exception as e:
                raise RuntimeError(f"Could not copy Gmail icon: {e}")


    fn = find_function(code, "configureOverlayView")
    if not fn:
        raise RuntimeError("configureOverlayView() not found")

    _, fn_open, fn_close = fn
    body = code[fn_open + 1:fn_close]

    loop_match = re.search(r"order\.forEachIndexed\s*\{", body)
    if not loop_match:
        raise RuntimeError("Original navigation button order loop not found")

    loop_open_rel = body.find("{", loop_match.start(), loop_match.end())
    if loop_open_rel < 0:
        raise RuntimeError("Navigation button loop opening brace not found")

    loop_close_rel = find_matching_brace(body, loop_open_rel)
    if loop_close_rel < 0:
        raise RuntimeError("Navigation button loop closing brace not found")

    insert_pos = fn_open + 1 + loop_close_rel + 1

    gmail_layout_patch = r"""

        // WINX_GMAIL_BUTTON_PATCH

        val winXGmailButton = FrameLayout(this).apply {
            isClickable = true
            isFocusable = true
            isFocusableInTouchMode = false
            isLongClickable = false

            val icon = ImageView(this@NavigationOverlayService).apply {
                setImageResource(R.drawable.gmail_custom)
                scaleType = ImageView.ScaleType.CENTER_INSIDE
                isClickable = false
                isFocusable = false
                isFocusableInTouchMode = false
                isLongClickable = false
            }

            addView(
                icon,
                FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    Gravity.CENTER
                ).apply {
                    val p = dpToPx(prefs.getInt("button_padding", 10))
                    setMargins(p, p, p, p)
                }
            )

            setOnClickListener {
                try {
                    val intent = packageManager.getLaunchIntentForPackage("com.google.android.gm")
                    if (intent != null) {
                        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(intent)
                    }
                } catch (_: Exception) {
                }
            }
        }

        val winXGmailParams = if (isVerticalBar) {
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                hitboxSize,
                0f
            )
        } else {
            LinearLayout.LayoutParams(
                hitboxSize,
                LinearLayout.LayoutParams.MATCH_PARENT,
                0f
            )
        }

        if (!shouldSwap) {
            // Back | Home | Gmail | SPACE | Clock | Recent
            container.addView(winXGmailButton, 2, winXGmailParams)
        }

        // WINX_GMAIL_BUTTON_PATCH_END
"""
    code = code[:insert_pos] + gmail_layout_patch + code[insert_pos:]


# ============================================================
# 5.5. PROTECT showOverlayAnimated() ONLY WHILE WIN X IS ACTIVE
#      This keeps the original swipe/reveal logic intact everywhere else.
# ============================================================

if "WINX_SHOW_ANIMATED_PROTECTION" not in code:
    fn = find_function(code, "showOverlayAnimated")
    if not fn:
        raise RuntimeError("showOverlayAnimated() not found")

    _, fn_open, _ = fn
    guard = """
        // WINX_SHOW_ANIMATED_PROTECTION
        if (isWinXLauncher) return

"""
    code = code[:fn_open + 1] + guard + code[fn_open + 1:]


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

    # Find the complete order.forEachIndexed { ... } block first.
    # We deliberately insert the clock AFTER that block, never inside it.
    loop_match = re.search(
        r"order\.forEachIndexed\s*\{",
        body,
    )
    if not loop_match:
        raise RuntimeError("Original navigation button order loop not found")

    loop_open_rel = body.find("{", loop_match.start(), loop_match.end())
    if loop_open_rel < 0:
        raise RuntimeError("Navigation button loop opening brace not found")

    loop_close_rel = find_matching_brace(body, loop_open_rel)
    if loop_close_rel < 0:
        raise RuntimeError("Navigation button loop closing brace not found")

    insert_pos = fn_open + 1 + loop_close_rel + 1

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
                hitboxSize,
                hitboxSize,
                0f
            ).apply {
                gravity = Gravity.CENTER
            }
        } else {
            LinearLayout.LayoutParams(
                dpToPx(50),
                LinearLayout.LayoutParams.MATCH_PARENT,
                0f
            ).apply {
                gravity = Gravity.CENTER_VERTICAL
            }
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
            // Recent | Clock | SPACE | Gmail | Home | Back
            container.addView(winXClockView, 1, winXClockParams)
            container.addView(winXSpacer, 2, winXSpacerParams)
            container.addView(winXGmailButton, 3, winXGmailParams)
        } else {
            // Back | Home | Gmail | SPACE | Clock | Recent
            container.addView(winXSpacer, 3, winXSpacerParams)
            container.addView(winXClockView, 4, winXClockParams)
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
        print("Warning: container.gravity line not found; leaving original gravity")


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
# 9. SAVE
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
print("Clock: 9sp time / 7sp date / 50dp / centered / non-touch")
print("Gmail: external gmail_custom.png copied to res/drawable")
print("Swipe: ORIGINAL SWIPE/REVEAL CODE PRESERVED")
print("================================================")
print("PATCH COMPLETE")
print("================================================")
