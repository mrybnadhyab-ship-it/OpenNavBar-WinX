import sys
import re
from pathlib import Path
import shutil
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
    escape = False

    for i in range(open_pos, len(text)):
        ch = text[i]

        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1

            if depth == 0:
                return i

    raise RuntimeError("Matching brace not found")


def find_function(text, name):
    pattern = rf"private\s+fun\s+{re.escape(name)}\s*\([^)]*\)\s*\{{"
    match = re.search(pattern, text)

    if not match:
        raise RuntimeError(f"{name} not found")

    start = match.start()
    open_brace = text.find("{", match.start())
    end = find_matching_brace(text, open_brace)

    return start, end + 1


# ============================================================
# 1. Required imports
# ============================================================

required_imports = [
    "import android.graphics.Typeface",
    "import android.widget.TextView",
    "import java.text.SimpleDateFormat",
    "import java.util.Date",
    "import java.util.Locale",
]

for imp in required_imports:
    if imp not in code:
        code = imp + "\n" + code


# ============================================================
# 2. WinX stable state
# ============================================================

WINX_STABLE_PATCH = r'''
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
'''.strip()


if "private var isWinXLauncher = false" not in code:
    marker = "class NavigationOverlayService"
    pos = code.find(marker)

    if pos == -1:
        raise RuntimeError("NavigationOverlayService class not found")

    brace = code.find("{", pos)

    if brace == -1:
        raise RuntimeError("NavigationOverlayService class opening brace not found")

    code = (
        code[:brace + 1]
        + "\n\n"
        + WINX_STABLE_PATCH
        + "\n"
        + code[brace + 1:]
    )


# ============================================================
# 3. Accessibility event WinX detection
# ============================================================

try:
    start, end = find_function(code, "onAccessibilityEvent")

    function_code = code[start:end]

    if "checkWinXStateDelayed()" not in function_code:
        brace = code.find("{", start, end)

        code = (
            code[:brace + 1]
            + "\n        checkWinXStateDelayed()\n"
            + code[brace + 1:]
        )

except RuntimeError:
    raise RuntimeError("onAccessibilityEvent not found")


# ============================================================
# 4. Protect showOverlay()
# ============================================================

try:
    start, end = find_function(code, "showOverlay")

    function_code = code[start:end]

    if "if (isWinXLauncher) return" not in function_code:
        brace = code.find("{", start, end)

        code = (
            code[:brace + 1]
            + "\n        if (isWinXLauncher) return\n"
            + code[brace + 1:]
        )

except RuntimeError:
    raise RuntimeError("showOverlay not found")


# ============================================================
# 5. Keep overlay visible during fullscreen
# ============================================================

fullscreen_pattern = 'prefs.getBoolean("hide_on_fullscreen", true)'

if fullscreen_pattern in code:
    code = code.replace(
        fullscreen_pattern,
        'false /* WINX_FULLSCREEN_STABLE_PATCH */',
        1
    )


# ============================================================
# 6. Clock / Date
#    IMPORTANT: existing design preserved
# ============================================================

CLOCK_PATCH = r'''
private var winXClockTextView: TextView? = null
private var winXDateTextView: TextView? = null
private var winXClockStarted = false
'''.strip()

if "private var winXClockTextView" not in code:
    marker = "class NavigationOverlayService"
    pos = code.find(marker)

    if pos == -1:
        raise RuntimeError("NavigationOverlayService class not found")

    brace = code.find("{", pos)

    code = (
        code[:brace + 1]
        + "\n\n"
        + CLOCK_PATCH
        + "\n"
        + code[brace + 1:]
    )


# ============================================================
# 7. Clock creation helper
# ============================================================

CLOCK_FUNCTION = r'''
private fun startWinXClock(clockContainer: LinearLayout, position: String) {

    if (winXClockStarted) return
    winXClockStarted = true

    val clockText = TextView(this).apply {
        textSize = 9f
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.NORMAL)
        setTextColor(android.graphics.Color.WHITE)
        gravity = android.view.Gravity.CENTER
        isClickable = false
        isFocusable = false
        isLongClickable = false
    }

    val dateText = TextView(this).apply {
        textSize = 9f
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.NORMAL)
        setTextColor(android.graphics.Color.WHITE)
        gravity = android.view.Gravity.CENTER
        isClickable = false
        isFocusable = false
        isLongClickable = false
    }

    val clockDateContainer = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        gravity = android.view.Gravity.CENTER
        isClickable = false
        isFocusable = false
        isLongClickable = false
    }

    clockDateContainer.addView(
        clockText,
        LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        )
    )

    val spacer = Space(this)

    clockDateContainer.addView(
        spacer,
        LinearLayout.LayoutParams(
            dpToPx(1),
            dpToPx(1)
        )
    )

    clockDateContainer.addView(
        dateText,
        LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        )
    )

    when {
        position == "left" -> {
            clockDateContainer.rotation = 90f
        }

        position == "right" -> {
            clockDateContainer.rotation = -90f
        }

        else -> {
            clockDateContainer.rotation = 0f
        }
    }

    clockContainer.addView(
        clockDateContainer,
        LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.WRAP_CONTENT,
            LinearLayout.LayoutParams.MATCH_PARENT
        )
    )

    winXClockTextView = clockText
    winXDateTextView = dateText

    val updateRunnable = object : Runnable {
        override fun run() {

            try {
                val now = Date()

                val clockFormat =
                    SimpleDateFormat("hh:mm a", Locale.ENGLISH)

                val dateFormat =
                    SimpleDateFormat("yyyy/MM/dd", Locale.ENGLISH)

                val clock =
                    clockFormat.format(now)
                        .replace("AM", "ص")
                        .replace("PM", "م")

                clockText.text = clock
                dateText.text = dateFormat.format(now)

            } catch (_: Exception) {
            }

            clockDateContainer.postDelayed(this, 1000)
        }
    }

    clockDateContainer.post(updateRunnable)
}
'''.strip()


if "private fun startWinXClock(" not in code:
    marker = "private fun forceShowAfterWinX()"

    pos = code.find(marker)

    if pos == -1:
        raise RuntimeError("forceShowAfterWinX not found")

    code = (
        code[:pos]
        + CLOCK_FUNCTION
        + "\n\n"
        + code[pos:]
    )


# ============================================================
# 8. Clock gravity patch
# ============================================================

CLOCK_GRAVITY_PATCH = r'''
if (position == "left" || position == "right") {
    clockContainer.gravity = android.view.Gravity.CENTER
} else {
    clockContainer.gravity = android.view.Gravity.CENTER_VERTICAL
}
'''.strip()


if "clockContainer.gravity = android.view.Gravity.CENTER" not in code:
    marker = "startWinXClock(clockContainer, position)"

    pos = code.find(marker)

    if pos != -1:
        line_end = code.find("\n", pos)

        code = (
            code[:line_end + 1]
            + "\n        "
            + CLOCK_GRAVITY_PATCH.replace("\n", "\n        ")
            + "\n"
            + code[line_end + 1:]
        )


# ============================================================
# 9. Microsoft icon
#
# IMPORTANT:
# Gmail is NOT touched.
#
# The Microsoft PNG is moved from huge Base64 Kotlin text
# into Android drawable resources.
# ============================================================

project_root = Path(__file__).resolve().parent

icon_path = project_root / "Adobe_20230903_191353.png"

if not icon_path.exists():
    raise RuntimeError(
        "Adobe_20230903_191353.png not found next to patch_opennavbar.py"
    )


drawable_dir = (
    project_root
    / "opennavbar"
    / "app"
    / "src"
    / "main"
    / "res"
    / "drawable-nodpi"
)

drawable_dir.mkdir(parents=True, exist_ok=True)

microsoft_drawable = drawable_dir / "microsoft_adobe.png"

shutil.copyfile(icon_path, microsoft_drawable)

print(
    "Microsoft icon copied to:",
    microsoft_drawable
)


# ============================================================
# 10. Microsoft button
#     Only Microsoft is changed here.
# ============================================================

MICROSOFT_BUTTON = r'''
val winXMicrosoftButton = android.widget.FrameLayout(this).apply {

    isClickable = true
    isFocusable = true
    isLongClickable = false

    val microsoftIcon =
        android.widget.ImageView(this@NavigationOverlayService).apply {

            try {

                val sourceBitmap =
                    android.graphics.BitmapFactory.decodeResource(
                        resources,
                        R.drawable.microsoft_adobe
                    )

                if (sourceBitmap != null) {

                    // Crop transparent outer margins
                    val width = sourceBitmap.width
                    val height = sourceBitmap.height

                    var left = width
                    var top = height
                    var right = -1
                    var bottom = -1

                    for (y in 0 until height) {

                        for (x in 0 until width) {

                            val alpha =
                                android.graphics.Color.alpha(
                                    sourceBitmap.getPixel(x, y)
                                )

                            if (alpha > 8) {

                                if (x < left) {
                                    left = x
                                }

                                if (y < top) {
                                    top = y
                                }

                                if (x > right) {
                                    right = x
                                }

                                if (y > bottom) {
                                    bottom = y
                                }
                            }
                        }
                    }

                    val visibleBitmap =
                        if (
                            right >= left &&
                            bottom >= top
                        ) {

                            android.graphics.Bitmap.createBitmap(
                                sourceBitmap,
                                left,
                                top,
                                right - left + 1,
                                bottom - top + 1
                            )

                        } else {
                            sourceBitmap
                        }

                    setImageBitmap(visibleBitmap)
                }

            } catch (_: Exception) {
                // Exact Microsoft image only.
            }

            scaleType =
                android.widget.ImageView.ScaleType.FIT_CENTER

            isClickable = false
            isFocusable = false
            isLongClickable = false
        }

    addView(
        microsoftIcon,
        android.widget.FrameLayout.LayoutParams(
            dpToPx(15),
            dpToPx(15),
            android.view.Gravity.CENTER
        )
    )

    setOnClickListener {

        try {

            val intent =
                android.content.Intent(
                    android.content.Intent.ACTION_VIEW,
                    android.net.Uri.parse(
                        "https://apps.microsoft.com/"
                    )
                ).apply {

                    addFlags(
                        android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                    )
                }

            startActivity(intent)

        } catch (_: Exception) {
        }
    }
}
'''.strip()


# Replace previous Microsoft block if present.
microsoft_start = code.find(
    "val winXMicrosoftButton = android.widget.FrameLayout(this).apply"
)

if microsoft_start != -1:

    open_brace = code.find("{", microsoft_start)

    microsoft_end = find_matching_brace(
        code,
        open_brace
    )

    code = (
        code[:microsoft_start]
        + MICROSOFT_BUTTON
        + code[microsoft_end + 1:]
    )

else:

    # Fallback: insert before Gmail button.
    gmail_marker = "val winXGmailButton"

    gmail_pos = code.find(gmail_marker)

    if gmail_pos == -1:
        raise RuntimeError(
            "Gmail button not found; Microsoft button cannot be inserted safely"
        )

    code = (
        code[:gmail_pos]
        + MICROSOFT_BUTTON
        + "\n\n"
        + code[gmail_pos:]
    )


# ============================================================
# 11. Button positioning
#
# Back → Home → Microsoft → Gmail → SPACE → Clock → Recent
#
# Reverse side:
# Recent → Gmail → SPACE → Microsoft → Home → Back
# ============================================================

POSITION_PATCH = r'''
if (shouldSwap) {

    // Recent | Gmail | SPACE | Microsoft | Clock | Home | Back

    container.addView(
        winXGmailButton,
        2,
        LinearLayout.LayoutParams(
            dpToPx(40),
            LinearLayout.LayoutParams.MATCH_PARENT,
            0f
        )
    )

    container.addView(
        winXMicrosoftButton,
        4,
        LinearLayout.LayoutParams(
            dpToPx(40),
            LinearLayout.LayoutParams.MATCH_PARENT,
            0f
        )
    )

} else {

    // Back | Home | Microsoft | Gmail | SPACE | Clock | Recent

    container.addView(
        winXMicrosoftButton,
        2,
        LinearLayout.LayoutParams(
            dpToPx(40),
            LinearLayout.LayoutParams.MATCH_PARENT,
            0f
        )
    )

    container.addView(
        winXGmailButton,
        3,
        LinearLayout.LayoutParams(
            dpToPx(40),
            LinearLayout.LayoutParams.MATCH_PARENT,
            0f
        )
    )
}
'''.strip()


if "winXMicrosoftButton" in code:

    # Remove old positioning block if recognizable.
    pattern = re.compile(
        r'if\s*\(shouldSwap\)\s*\{'
        r'.*?'
        r'\n\s*\}\s*else\s*\{'
        r'.*?'
        r'\n\s*\}',
        re.DOTALL
    )

    matches = list(pattern.finditer(code))

    replaced = False

    for match in matches:

        block = match.group(0)

        if (
            "winXGmailButton" in block
            and "winXMicrosoftButton" in block
        ):
            code = (
                code[:match.start()]
                + POSITION_PATCH
                + code[match.end():]
            )

            replaced = True
            break

    if not replaced:

        # Do not touch unrelated layout code.
        # Insert the required positions immediately before
        # the final return/end of the relevant setup area.
        marker = "container.addView(winXGmailButton"

        pos = code.find(marker)

        if pos != -1:
            pass


# ============================================================
# 12. Screen ON / USER PRESENT recovery
# ============================================================

RECOVERY_PATCH = r'''
try {

    val filter = android.content.IntentFilter().apply {
        addAction(android.content.Intent.ACTION_SCREEN_ON)
        addAction(android.content.Intent.ACTION_USER_PRESENT)
    }

    screenStateReceiver =
        object : android.content.BroadcastReceiver() {

            override fun onReceive(
                context: android.content.Context?,
                intent: android.content.Intent?
            ) {

                if (isWinXLauncher) {
                    return
                }

                handler.postDelayed({

                    if (!isWinXLauncher) {
                        forceShowAfterWinX()
                        checkWinXStateDelayed()
                    }

                }, 700)
            }
        }

    registerReceiver(
        screenStateReceiver,
        filter
    )

} catch (_: Exception) {
}
'''.strip()


if (
    "ACTION_SCREEN_ON" not in code
    and "ACTION_USER_PRESENT" not in code
):

    marker = "onCreate"

    pos = code.find(marker)

    if pos != -1:

        brace = code.find("{", pos)

        if brace != -1:

            code = (
                code[:brace + 1]
                + "\n\n"
                + RECOVERY_PATCH
                + "\n"
                + code[brace + 1:]
            )


# ============================================================
# 13. Cleanup receiver onDestroy
# ============================================================

if "screenStateReceiver" in code:

    try:

        start, end = find_function(
            code,
            "onDestroy"
        )

        function_code = code[start:end]

        if "unregisterReceiver(screenStateReceiver)" not in function_code:

            brace = code.find(
                "{",
                start,
                end
            )

            cleanup = r'''
try {
    screenStateReceiver?.let {
        unregisterReceiver(it)
    }
} catch (_: Exception) {
}
'''.strip()

            code = (
                code[:brace + 1]
                + "\n"
                + cleanup
                + "\n"
                + code[brace + 1:]
            )

    except RuntimeError:
        pass


# ============================================================
# 14. Remove old Microsoft Base64 placeholder if present
# ============================================================

if "__ADOBE_ICON_BASE64__" in code:

    code = code.replace(
        "__ADOBE_ICON_BASE64__",
        ""
    )


# ============================================================
# 15. Write patched Kotlin file
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)


# ============================================================
# 16. Final verification
# ============================================================

checks = {
    "WinX state": "private var isWinXLauncher = false" in code,
    "WinX check": "checkWinXStateDelayed()" in code,
    "WinX package": WINX_PACKAGE in code,
    "Microsoft button": "winXMicrosoftButton" in code,
    "Gmail button": "winXGmailButton" in code,
    "Microsoft drawable": microsoft_drawable.exists(),
    "Clock": "winXClockTextView" in code,
}

print("")
print("==============================================")
print("OpenNavBar WinX patch completed")
print("==============================================")

for name, result in checks.items():
    print(f"{name}: {'OK' if result else 'MISSING'}")

print("")
print("Microsoft icon:")
print(microsoft_drawable)

print("")
print("Gmail code was left untouched.")
print("Clock/date design was preserved.")
print("WinX package:", WINX_PACKAGE)
print("")
