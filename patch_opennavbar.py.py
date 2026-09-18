")
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
import re
import sys
from pathlib import Path

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"


def find_matching_brace(text, start):
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        c = text[i]

        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue

        if c == '"':
            in_string = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i

    raise RuntimeError("Matching brace not found")


def find_function(text, signature):
    start = text.find(signature)
    if start < 0:
        raise RuntimeError(f"Function not found: {signature}")

    brace = text.find("{", start)
    if brace < 0:
        raise RuntimeError(f"Opening brace not found: {signature}")

    end = find_matching_brace(text, brace)
    return start, brace, end


def add_import(text, import_line):
    if import_line in text:
        return text

    package_match = re.search(r"^package .+$", text, re.MULTILINE)
    if not package_match:
        raise RuntimeError("package declaration not found")

    pos = package_match.end()
    return text[:pos] + "\n\n" + import_line + text[pos:]


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
        sys.exit(1)

    kt_path = Path(sys.argv[1])

    if not kt_path.exists():
        raise RuntimeError(f"Target Kotlin file not found: {kt_path}")

    text = kt_path.read_text(encoding="utf-8")

    # ---------------------------------------------------------
    # Imports
    # ---------------------------------------------------------

    imports = [
        "import android.graphics.Typeface",
        "import android.widget.TextView",
        "import java.text.SimpleDateFormat",
        "import java.util.Date",
        "import java.util.Locale",
    ]

    for imp in imports:
        text = add_import(text, imp)

    # ---------------------------------------------------------
    # WinX state variables
    # ---------------------------------------------------------

    if "private var isWinXLauncher = false" not in text:
        marker = "class NavigationOverlayService"
        pos = text.find(marker)

        if pos < 0:
            raise RuntimeError("NavigationOverlayService class not found")

        brace = text.find("{", pos)

        if brace < 0:
            raise RuntimeError("NavigationOverlayService opening brace not found")

        variables = """

    private var isWinXLauncher = false
    private var winXCheckRunnable: Runnable? = null
"""

        text = text[:brace + 1] + variables + text[brace + 1:]

    # ---------------------------------------------------------
    # WinX foreground package detection
    # ---------------------------------------------------------

    if "private fun getCurrentForegroundPackage()" not in text:

        marker = "private fun getCurrentForegroundPackage()"

        method = """
    private fun getCurrentForegroundPackage(): String {
        return rootInActiveWindow?.packageName?.toString() ?: ""
    }

    private fun checkWinXStateDelayed() {
        winXCheckRunnable?.let {
            handler.removeCallbacks(it)
        }

        winXCheckRunnable = Runnable {
            val currentPackage = getCurrentForegroundPackage()
            val shouldHide = currentPackage == WINX_PACKAGE

            if (shouldHide) {
                if (!isWinXLauncher) {
                    isWinXLauncher = true

                    try {
                        navBarCheckRunnable?.let {
                            handler.removeCallbacks(it)
                        }
                    } catch (_: Exception) {
                    }

                    try {
                        insetsDebounce?.let {
                            handler.removeCallbacks(it)
                        }
                    } catch (_: Exception) {
                    }

                    try {
                        autoHideRunnable?.let {
                            handler.removeCallbacks(it)
                        }
                    } catch (_: Exception) {
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

        handler.postDelayed(winXCheckRunnable!!, 100)
    }

    private fun forceShowAfterWinX() {
        try {
            overlayView?.visibility = View.VISIBLE
            overlayView?.alpha = 1f
            overlayView?.translationX = 0f
            overlayView?.translationY = 0f

            isHidden = false

            showOverlay()

        } catch (_: Exception) {
        }
    }

"""

        # Put methods before onAccessibilityEvent
        accessibility_pos = text.find("override fun onAccessibilityEvent")

        if accessibility_pos < 0:
            raise RuntimeError("onAccessibilityEvent not found")

        text = text[:accessibility_pos] + method + text[accessibility_pos:]

    # ---------------------------------------------------------
    # Accessibility event hook
    # ---------------------------------------------------------

    signature = "override fun onAccessibilityEvent(event: AccessibilityEvent?)"

    start, brace, end = find_function(text, signature)

    body = text[brace + 1:end]

    if "checkWinXStateDelayed()" not in body:
        body = """
        checkWinXStateDelayed()

""" + body

    text = text[:brace + 1] + body + text[end:]

    # ---------------------------------------------------------
    # Protect showOverlay()
    # ---------------------------------------------------------

    try:
        start, brace, end = find_function(text, "private fun showOverlay()")
        body = text[brace + 1:end]

        if "if (isWinXLauncher) return" not in body:
            body = """

        if (isWinXLauncher) return

""" + body

        text = text[:brace + 1] + body + text[end:]

    except RuntimeError:
        pass

    # ---------------------------------------------------------
    # Clock / Date variables
    # ---------------------------------------------------------

    if "private var winXClockTextView: TextView? = null" not in text:

        marker = "class NavigationOverlayService"
        pos = text.find(marker)
        brace = text.find("{", pos)

        variables = """

    private var winXClockTextView: TextView? = null
    private var winXDateTextView: TextView? = null
    private var winXClockStarted = false

"""

        text = text[:brace + 1] + variables + text[brace + 1:]

    # ---------------------------------------------------------
    # Clock updater
    # ---------------------------------------------------------

    if "private fun updateWinXClock()" not in text:

        method = """
    private fun updateWinXClock() {
        val now = Date()

        val timeFormat = SimpleDateFormat(
            "hh:mm a",
            Locale.getDefault()
        )

        val dateFormat = SimpleDateFormat(
            "yyyy/MM/dd",
            Locale.getDefault()
        )

        val time = timeFormat.format(now)
            .replace("AM", "ص")
            .replace("PM", "م")

        val date = dateFormat.format(now)

        winXClockTextView?.text = time
        winXDateTextView?.text = date
    }

    private fun startWinXClock() {
        if (winXClockStarted) return

        winXClockStarted = true

        val runnable = object : Runnable {
            override fun run() {
                updateWinXClock()
                handler.postDelayed(this, 1000)
            }
        }

        handler.post(runnable)
    }

"""

        pos = text.find("override fun onAccessibilityEvent")

        if pos < 0:
            raise RuntimeError("Cannot insert clock methods")

        text = text[:pos] + method + text[pos:]

    # ---------------------------------------------------------
    # Clock creation inside configureOverlayView()
    # ---------------------------------------------------------

    if "winXClockTextView = TextView(" not in text:

        try:
            start, brace, end = find_function(
                text,
                "private fun configureOverlayView"
            )

            body = text[brace + 1:end]

            marker = "order.forEachIndexed"

            marker_pos = body.find(marker)

            if marker_pos < 0:
                raise RuntimeError(
                    "order.forEachIndexed not found in configureOverlayView"
                )

            insert_pos = body.find("\n", marker_pos)

            clock_code = """

        // WinX Clock + Date
        val clockContainer = LinearLayout(this)
        clockContainer.orientation = LinearLayout.VERTICAL
        clockContainer.gravity = Gravity.CENTER
        clockContainer.isClickable = false
        clockContainer.isFocusable = false

        winXClockTextView = TextView(this)
        winXClockTextView?.apply {
            textSize = 9f
            typeface = Typeface.DEFAULT
            gravity = Gravity.CENTER
            isClickable = false
            isFocusable = false
        }

        winXDateTextView = TextView(this)
        winXDateTextView?.apply {
            textSize = 9f
            typeface = Typeface.DEFAULT
            gravity = Gravity.CENTER
            isClickable = false
            isFocusable = false
        }

        clockContainer.addView(
            winXClockTextView,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )

        clockContainer.addView(
            winXDateTextView,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )

        val clockParams = if (isVerticalBar) {
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                hitboxSize
            )
        } else {
            LinearLayout.LayoutParams(
                50.dpToPx(),
                LinearLayout.LayoutParams.MATCH_PARENT
            )
        }

        clockParams.gravity = Gravity.CENTER

        container.addView(clockContainer, clockParams)

        startWinXClock()
        updateWinXClock()

"""

            body = body[:insert_pos] + clock_code + body[insert_pos:]

            text = text[:brace + 1] + body + text[end:]

        except RuntimeError as e:
            print(f"Clock insertion skipped: {e}")

    # ---------------------------------------------------------
    # Overlay gravity
    # ---------------------------------------------------------

    gravity_old = "container.gravity = Gravity.CENTER"

    if gravity_old in text:
        text = text.replace(
            gravity_old,
            "container.gravity = if (isVerticalBar) " +
            "Gravity.CENTER_HORIZONTAL else Gravity.CENTER_VERTICAL"
        )

    # ---------------------------------------------------------
    # Protect showOverlayAnimated()
    # ---------------------------------------------------------

    try:
        start, brace, end = find_function(
            text,
            "private fun showOverlayAnimated"
        )

        body = text[brace + 1:end]

        if "if (isWinXLauncher) return" not in body:
            body = """

        if (isWinXLauncher) return

""" + body

        text = text[:brace + 1] + body + text[end:]

    except RuntimeError:
        pass

    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------

    try:
        start, brace, end = find_function(text, "override fun onDestroy")
        body = text[brace + 1:end]

        cleanup = """
        winXClockTextView = null
        winXDateTextView = null
        winXClockStarted = false

"""

        if "winXClockTextView = null" not in body:
            body = cleanup + body

        text = text[:brace + 1] + body + text[end:]

    except RuntimeError:
        pass

    # ---------------------------------------------------------
    # Save
    # ---------------------------------------------------------

    kt_path.write_text(text, encoding="utf-8")

    print("========================================")
    print("OpenNavBar-WinX patch applied")
    print("WinX package:", WINX_PACKAGE)
    print("Clock: 9sp")
    print("Date: 9sp")
    print("Gmail: NOT ADDED")
    print("========================================")


if __name__ == "__main__":
    main()
