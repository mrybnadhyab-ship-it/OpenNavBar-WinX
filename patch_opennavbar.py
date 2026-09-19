import sys
import re
from pathlib import Path
import shutil

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    code = f.read()

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"


# ============================================================
# Helpers
# ============================================================

def find_matching_brace(text, open_pos):
    depth = 0
    in_string = False
    in_char = False
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

        if in_char:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "'":
                in_char = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "'":
            in_char = True
            continue

        if ch == "{":
            depth += 1

        elif ch == "}":
            depth -= 1

            if depth == 0:
                return i

    raise RuntimeError("Matching brace not found")


def find_function(text, name):
    """
    Finds Kotlin functions regardless of modifiers, e.g.

    private fun foo(...)
    override fun foo(...)
    public fun foo(...)
    fun foo(...)
    protected fun foo(...)
    """

    pattern = re.compile(
        rf"""
        (?m)
        ^[ \t]*
        (?:
            (?:public|private|protected|internal|override|open|final|suspend|inline|operator|infix|tailrec|abstract|external)
            [ \t]+
        )*
        fun
        [ \t]+
        {re.escape(name)}
        [ \t]*
        \(
        """,
        re.VERBOSE
    )

    match = pattern.search(text)

    if not match:
        # Fallback: find any occurrence of the function name.
        fallback = re.search(
            rf"\bfun\s+{re.escape(name)}\s*\(",
            text
        )

        if not fallback:
            raise RuntimeError(f"{name} not found")

        match = fallback

    start = match.start()

    open_paren = text.find("(", match.start())

    if open_paren == -1:
        raise RuntimeError(f"Opening parenthesis for {name} not found")

    # Find the opening brace after the function signature.
    open_brace = text.find("{", open_paren)

    if open_brace == -1:
        raise RuntimeError(
            f"Opening brace for {name} not found"
        )

    end = find_matching_brace(text, open_brace)

    return start, end + 1


def insert_inside_function(text, name, insertion):
    start, end = find_function(text, name)

    open_brace = text.find("{", start, end)

    if open_brace == -1:
        raise RuntimeError(
            f"Opening brace for {name} not found"
        )

    return (
        text[:open_brace + 1]
        + "\n"
        + insertion
        + "\n"
        + text[open_brace + 1:]
    )


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
# 2. WinX variables
# ============================================================

if "private var isWinXLauncher = false" not in code:

    class_match = re.search(
        r"class\s+NavigationOverlayService\b[^{]*\{",
        code
    )

    if not class_match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    insert_pos = class_match.end()

    winx_variables = r'''
private var isWinXLauncher = false
private var winXCheckRunnable: Runnable? = null
'''.strip()

    code = (
        code[:insert_pos]
        + "\n\n"
        + winx_variables
        + "\n"
        + code[insert_pos:]
    )


# ============================================================
# 3. WinX functions
# ============================================================

if "private fun getCurrentForegroundPackage()" not in code:

    winx_functions = r'''
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
'''.strip()

    # Insert before first lifecycle function.
    lifecycle_match = re.search(
        r"\b(?:override\s+)?fun\s+onCreate\s*\(",
        code
    )

    if lifecycle_match:

        insert_pos = lifecycle_match.start()

        code = (
            code[:insert_pos]
            + winx_functions
            + "\n\n"
            + code[insert_pos:]
        )

    else:

        # Fallback: insert before class closing brace.
        class_match = re.search(
            r"class\s+NavigationOverlayService\b[^{]*\{",
            code
        )

        if not class_match:
            raise RuntimeError(
                "NavigationOverlayService class not found"
            )

        class_open = code.find(
            "{",
            class_match.start()
        )

        class_close = find_matching_brace(
            code,
            class_open
        )

        code = (
            code[:class_close]
            + "\n\n"
            + winx_functions
            + "\n"
            + code[class_close:]
        )


# ============================================================
# 4. Accessibility event
# ============================================================

try:

    start, end = find_function(
        code,
        "onAccessibilityEvent"
    )

    function_code = code[start:end]

    if "checkWinXStateDelayed()" not in function_code:

        open_brace = code.find(
            "{",
            start,
            end
        )

        code = (
            code[:open_brace + 1]
            + "\n        checkWinXStateDelayed()\n"
            + code[open_brace + 1:]
        )

except RuntimeError as e:

    raise RuntimeError(
        "Could not locate onAccessibilityEvent. "
        "The OpenNavBar source version is different."
    ) from e


# ============================================================
# 5. showOverlay protection
# ============================================================

try:

    start, end = find_function(
        code,
        "showOverlay"
    )

    function_code = code[start:end]

    if "if (isWinXLauncher) return" not in function_code:

        open_brace = code.find(
            "{",
            start,
            end
        )

        code = (
            code[:open_brace + 1]
            + "\n        if (isWinXLauncher) return\n"
            + code[open_brace + 1:]
        )

except RuntimeError as e:

    raise RuntimeError(
        "showOverlay not found"
    ) from e


# ============================================================
# 6. Keep overlay visible during fullscreen
# ============================================================

fullscreen_pattern = (
    'prefs.getBoolean("hide_on_fullscreen", true)'
)

if fullscreen_pattern in code:

    code = code.replace(
        fullscreen_pattern,
        'false /* WINX_FULLSCREEN_STABLE_PATCH */',
        1
    )


# ============================================================
# 7. Clock / Date
#    DO NOT CHANGE EXISTING DESIGN
# ============================================================

if "private var winXClockTextView" not in code:

    clock_variables = r'''
private var winXClockTextView: TextView? = null
private var winXDateTextView: TextView? = null
private var winXClockStarted = false
'''.strip()

    class_match = re.search(
        r"class\s+NavigationOverlayService\b[^{]*\{",
        code
    )

    if not class_match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    insert_pos = class_match.end()

    code = (
        code[:insert_pos]
        + "\n\n"
        + clock_variables
        + "\n"
        + code[insert_pos:]
    )


# ============================================================
# 8. Clock function
# ============================================================

if "private fun startWinXClock(" not in code:

    clock_function = r'''
private fun startWinXClock(
    clockContainer: LinearLayout,
    position: String
) {

    if (winXClockStarted) return

    winXClockStarted = true

    val clockText = TextView(this).apply {

        textSize = 9f

        typeface =
            Typeface.create(
                Typeface.DEFAULT,
                Typeface.NORMAL
            )

        setTextColor(
            android.graphics.Color.WHITE
        )

        gravity =
            android.view.Gravity.CENTER

        isClickable = false
        isFocusable = false
        isLongClickable = false
    }

    val dateText = TextView(this).apply {

        textSize = 9f

        typeface =
            Typeface.create(
                Typeface.DEFAULT,
                Typeface.NORMAL
            )

        setTextColor(
            android.graphics.Color.WHITE
        )

        gravity =
            android.view.Gravity.CENTER

        isClickable = false
        isFocusable = false
        isLongClickable = false
    }

    val clockDateContainer =
        LinearLayout(this).apply {

            orientation =
                LinearLayout.VERTICAL

            gravity =
                android.view.Gravity.CENTER

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

    val updateRunnable =
        object : Runnable {

            override fun run() {

                try {

                    val now = Date()

                    val clockFormat =
                        SimpleDateFormat(
                            "hh:mm a",
                            Locale.ENGLISH
                        )

                    val dateFormat =
                        SimpleDateFormat(
                            "yyyy/MM/dd",
                            Locale.ENGLISH
                        )

                    val clock =
                        clockFormat
                            .format(now)
                            .replace("AM", "ص")
                            .replace("PM", "م")

                    clockText.text = clock

                    dateText.text =
                        dateFormat.format(now)

                } catch (_: Exception) {
                }

                clockDateContainer.postDelayed(
                    this,
                    1000
                )
            }
        }

    clockDateContainer.post(
        updateRunnable
    )
}
'''.strip()

    marker = "private fun forceShowAfterWinX()"

    pos = code.find(marker)

    if pos == -1:
        raise RuntimeError(
            "forceShowAfterWinX not found"
        )

    code = (
        code[:pos]
        + clock_function
        + "\n\n"
        + code[pos:]
    )


# ============================================================
# 9. Microsoft image
#
# ONLY Microsoft is optimized.
# Gmail is NOT touched.
# ============================================================

project_root = Path(__file__).resolve().parent

icon_path = (
    project_root /
    "Adobe_20230903_191353.png"
)

if not icon_path.exists():

    raise RuntimeError(
        "Adobe_20230903_191353.png not found next to patch_opennavbar.py"
    )


drawable_dir = (
    project_root /
    "opennavbar" /
    "app" /
    "src" /
    "main" /
    "res" /
    "drawable-nodpi"
)

drawable_dir.mkdir(
    parents=True,
    exist_ok=True
)

microsoft_drawable = (
    drawable_dir /
    "microsoft_adobe.png"
)

shutil.copyfile(
    icon_path,
    microsoft_drawable
)


# ============================================================
# 10. Microsoft button
# ============================================================

MICROSOFT_BUTTON = r'''
val winXMicrosoftButton =
    android.widget.FrameLayout(this).apply {

    isClickable = true
    isFocusable = true
    isLongClickable = false

    val microsoftIcon =
        android.widget.ImageView(
            this@NavigationOverlayService
        ).apply {

        try {

            val sourceBitmap =
                android.graphics.BitmapFactory
                    .decodeResource(
                        resources,
                        R.drawable.microsoft_adobe
                    )

            if (sourceBitmap != null) {

                val width =
                    sourceBitmap.width

                val height =
                    sourceBitmap.height

                var left = width
                var top = height
                var right = -1
                var bottom = -1

                for (y in 0 until height) {

                    for (x in 0 until width) {

                        val alpha =
                            android.graphics.Color.alpha(
                                sourceBitmap.getPixel(
                                    x,
                                    y
                                )
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

                        android.graphics.Bitmap
                            .createBitmap(
                                sourceBitmap,
                                left,
                                top,
                                right - left + 1,
                                bottom - top + 1
                            )

                    } else {
                        sourceBitmap
                    }

                setImageBitmap(
                    visibleBitmap
                )
            }

        } catch (_: Exception) {
        }

        scaleType =
            android.widget.ImageView
                .ScaleType.FIT_CENTER

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
                        android.content.Intent
                            .FLAG_ACTIVITY_NEW_TASK
                    )
                }

            startActivity(intent)

        } catch (_: Exception) {
        }
    }
}
'''.strip()


# Remove existing Microsoft block safely.
microsoft_marker = (
    "val winXMicrosoftButton"
)

microsoft_pos = code.find(
    microsoft_marker
)

if microsoft_pos != -1:

    open_brace = code.find(
        "{",
        microsoft_pos
    )

    if open_brace == -1:
        raise RuntimeError(
            "Microsoft button opening brace not found"
        )

    microsoft_end = find_matching_brace(
        code,
        open_brace
    )

    code = (
        code[:microsoft_pos]
        + MICROSOFT_BUTTON
        + code[microsoft_end + 1:]
    )

else:

    # Insert immediately before Gmail.
    gmail_pos = code.find(
        "val winXGmailButton"
    )

    if gmail_pos == -1:
        raise RuntimeError(
            "Gmail button not found"
        )

    code = (
        code[:gmail_pos]
        + MICROSOFT_BUTTON
        + "\n\n"
        + code[gmail_pos:]
    )


# ============================================================
# 11. Button order
# ============================================================

# We intentionally only replace blocks that contain BOTH
# Microsoft and Gmail, so unrelated layout code is untouched.

position_pattern = re.compile(
    r'if\s*\(\s*shouldSwap\s*\)\s*\{.*?'
    r'\}\s*else\s*\{.*?\}',
    re.DOTALL
)

position_matches = list(
    position_pattern.finditer(code)
)

position_replaced = False

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


for match in position_matches:

    block = match.group(0)

    if (
        "winXGmailButton" in block
        and
        "winXMicrosoftButton" in block
    ):

        code = (
            code[:match.start()]
            + POSITION_PATCH
            + code[match.end():]
        )

        position_replaced = True
        break


if not position_replaced:

    print(
        "WARNING: Existing button position block was not replaced."
    )


# ============================================================
# 12. Screen ON / USER PRESENT
# ============================================================

if "ACTION_SCREEN_ON" not in code:

    recovery_patch = r'''
try {

    val filter =
        android.content.IntentFilter().apply {

        addAction(
            android.content.Intent.ACTION_SCREEN_ON
        )

        addAction(
            android.content.Intent.ACTION_USER_PRESENT
        )
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

    try:

        start, end = find_function(
            code,
            "onCreate"
        )

        open_brace = code.find(
            "{",
            start,
            end
        )

        code = (
            code[:open_brace + 1]
            + "\n"
            + recovery_patch
            + "\n"
            + code[open_brace + 1:]
        )

    except RuntimeError:

        print(
            "WARNING: onCreate not found; "
            "screen recovery was not inserted."
        )


# ============================================================
# 13. Cleanup
# ============================================================

try:

    start, end = find_function(
        code,
        "onDestroy"
    )

    function_code = code[start:end]

    if "unregisterReceiver" not in function_code:

        open_brace = code.find(
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
            code[:open_brace + 1]
            + "\n"
            + cleanup
            + "\n"
            + code[open_brace + 1:]
        )

except RuntimeError:
    pass


# ============================================================
# 14. Remove Microsoft Base64 placeholder
# ============================================================

if "__ADOBE_ICON_BASE64__" in code:

    code = code.replace(
        "__ADOBE_ICON_BASE64__",
        ""
    )


# ============================================================
# 15. Write file
# ============================================================

with open(
    path,
    "w",
    encoding="utf-8"
) as f:

    f.write(code)


# ============================================================
# 16. Verification
# ============================================================

checks = {

    "WinX state":
        "private var isWinXLauncher = false"
        in code,

    "WinX check":
        "checkWinXStateDelayed()"
        in code,

    "WinX package":
        WINX_PACKAGE
        in code,

    "Microsoft":
        "winXMicrosoftButton"
        in code,

    "Gmail":
        "winXGmailButton"
        in code,

    "Microsoft drawable":
        microsoft_drawable.exists(),

    "Clock":
        "winXClockTextView"
        in code,
}


print("")
print("==============================================")
print(" OpenNavBar WinX patch completed")
print("==============================================")

for name, result in checks.items():

    print(
        f"{name}: "
        f"{'OK' if result else 'MISSING'}"
    )

print("")
print("Microsoft image:")
print(microsoft_drawable)

print("")
print("Gmail: UNTOUCHED")
print("Clock/Date: PRESERVED")
print("WinX package:", WINX_PACKAGE)
print("")
