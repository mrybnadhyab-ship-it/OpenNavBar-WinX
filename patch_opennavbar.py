import sys
import re
from pathlib import Path
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
        code = code.replace(
            anchor,
            anchor + "\n" + imp,
            1
        )


# ============================================================
# 2. LIGHT WIN-X STATE PATCH
#
# IMPORTANT:
# No rootInActiveWindow polling.
# No check after every accessibility event.
# Uses the package name supplied by the accessibility event.
# ============================================================

if "WINX_LIGHT_STATE_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    winx_patch = rf'''

    // WINX_LIGHT_STATE_PATCH

    private var isWinXLauncher = false
    private var winXCheckRunnable: Runnable? = null

    private fun checkWinXStateFromEvent(
        event: AccessibilityEvent?
    ) {{
        val eventPackage = event?.packageName?.toString()
            ?: return

        if (eventPackage == "{WINX_PACKAGE}") {{

            if (!isWinXLauncher) {{
                isWinXLauncher = true

                navBarCheckRunnable?.let {{
                    handler.removeCallbacks(it)
                }}

                insetsDebounce?.let {{
                    handler.removeCallbacks(it)
                }}

                autoHideRunnable?.let {{
                    handler.removeCallbacks(it)
                }}

                winXCheckRunnable?.let {{
                    handler.removeCallbacks(it)
                }}

                hideOverlay()
            }}

        }} else {{

            if (isWinXLauncher) {{
                isWinXLauncher = false
                forceShowAfterWinX()
            }}
        }}
    }}

    private fun scheduleWinXStateCheck(
        event: AccessibilityEvent?
    ) {{
        val eventType = event?.eventType
            ?: return

        if (
            eventType != AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED &&
            eventType != AccessibilityEvent.TYPE_WINDOWS_CHANGED
        ) {{
            return
        }}

        val packageName = event.packageName?.toString()
            ?: return

        winXCheckRunnable?.let {{
            handler.removeCallbacks(it)
        }}

        winXCheckRunnable = Runnable {{
            checkWinXStateFromEvent(event)
        }}

        handler.postDelayed(
            winXCheckRunnable!!,
            120L
        )
    }}

    private fun forceShowAfterWinX() {{
        val view = overlayView ?: return

        view.animate().cancel()

        autoHideRunnable?.let {{
            handler.removeCallbacks(it)
        }}

        autoHideRunnable = null

        view.visibility = View.VISIBLE
        view.alpha = 1f
        view.translationX = 0f
        view.translationY = 0f

        isHidden = false
        isFullscreenHidden = false

        disableRevealZoneTouch()
    }}

    // WINX_LIGHT_STATE_PATCH_END
'''

    code = (
        code[:match.end()]
        + winx_patch
        + code[match.end():]
    )


# ============================================================
# 3. LIGHT ACCESSIBILITY EVENT PATCH
#
# Only react to actual window changes.
# ============================================================

if "WINX_LIGHT_EVENT_PATCH" not in code:

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
        // WINX_LIGHT_EVENT_PATCH
        scheduleWinXStateCheck(event)
        // WINX_LIGHT_EVENT_PATCH_END

'''

    code = (
        code[:match.end()]
        + event_patch
        + code[match.end():]
    )


# ============================================================
# 4. PROTECT showOverlay()
# ============================================================

if "WINX_SHOW_OVERLAY_PROTECTION" not in code:

    match = re.search(
        r"(private\s+fun\s+showOverlay\s*\([^)]*\)\s*\{)",
        code,
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
# 5. KEEP OVERLAY VISIBLE IN FULLSCREEN
# ============================================================

if "WINX_FULLSCREEN_STABLE_PATCH" not in code:

    fullscreen_expr = (
        'prefs.getBoolean("hide_on_fullscreen", true)'
    )

    fullscreen_replacement = (
        'false /* WINX_FULLSCREEN_STABLE_PATCH */'
    )

    if fullscreen_expr in code:
        code = code.replace(
            fullscreen_expr,
            fullscreen_replacement,
            1
        )
    else:
        raise RuntimeError(
            "hide_on_fullscreen preference not found"
        )


# ============================================================
# 6. LIGHT CLOCK + DATE
#
# Old:
# every 1000 ms
#
# New:
# update immediately, then once at the next minute.
# ============================================================

if "WINX_LIGHT_CLOCK_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code,
    )

    if not match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    clock_patch = r'''

    // WINX_LIGHT_CLOCK_PATCH

    private var winXClockTextView: TextView? = null
    private var winXDateTextView: TextView? = null
    private var winXClockStarted = false

    private val winXClockRunnable = object : Runnable {

        override fun run() {

            try {

                val nowMillis = System.currentTimeMillis()
                val now = Date(nowMillis)

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

                winXClockTextView?.text = timeText
                winXDateTextView?.text = dateText

                /*
                 * The clock has no seconds.
                 * Therefore there is no reason to wake the
                 * service every second.
                 *
                 * Schedule the next update shortly after
                 * the next minute begins.
                 */
                val delay =
                    60_000L -
                    (nowMillis % 60_000L) +
                    100L

                handler.postDelayed(
                    this,
                    delay
                )

            } catch (_: Exception) {

                /*
                 * If something goes wrong, retry after
                 * one minute instead of continuously looping.
                 */
                handler.postDelayed(
                    this,
                    60_000L
                )
            }
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

                this.rotation = rotation

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
                includeFontPadding = false

                textSize = 9f

                typeface =
                    Typeface.DEFAULT

                setTextColor(textColor)

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
                includeFontPadding = false

                textSize = 9f

                typeface =
                    Typeface.DEFAULT

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

        val dateParams =
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).apply {
                topMargin = dpToPx(1)
            }

        clockLayout.addView(
            date,
            dateParams
        )

        winXClockTextView = clock
        winXDateTextView = date

        if (!winXClockStarted) {

            winXClockStarted = true

            handler.removeCallbacks(
                winXClockRunnable
            )

            handler.post(
                winXClockRunnable
            )
        }

        return clockLayout
    }

    // WINX_LIGHT_CLOCK_PATCH_END
'''

    code = (
        code[:match.end()]
        + clock_patch
        + code[match.end():]
    )


# ============================================================
# 7. CLOCK LAYOUT
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

    abs_add_end = (
        fn_open +
        1 +
        add_match.end()
    )

    tail = code[
        abs_add_end:
        fn_close
    ]

    loop_close_rel = tail.find("}")

    if loop_close_rel < 0:
        raise RuntimeError(
            "Navigation button loop end not found"
        )

    insert_pos = (
        abs_add_end +
        loop_close_rel +
        1
    )

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


        // ====================================================
        // GMAIL
        // ====================================================

        val winXGmailButton =
            android.widget.FrameLayout(this).apply {

                isClickable = true
                isFocusable = true
                isLongClickable = false

                val gmailIcon =
                    android.widget.ImageView(
                        this@NavigationOverlayService
                    ).apply {

                        try {

                            /*
                             * Use Gmail's installed application
                             * icon directly.
                             *
                             * This removes the huge Base64 Gmail
                             * image from the generated source and
                             * saves memory/code size.
                             */

                            setImageDrawable(
                                packageManager.getApplicationIcon(
                                    "com.google.android.gm"
                                )
                            )

                        } catch (_: Exception) {

                            setImageResource(
                                android.R.drawable.ic_dialog_email
                            )
                        }

                        scaleType =
                            android.widget.ImageView.ScaleType.CENTER_INSIDE

                        isClickable = false
                        isFocusable = false
                        isLongClickable = false
                    }

                addView(
                    gmailIcon,
                    android.widget.FrameLayout.LayoutParams(
                        dpToPx(16),
                        dpToPx(16),
                        android.view.Gravity.CENTER
                    )
                )

                setOnClickListener {

                    try {

                        val launchIntent =
                            android.content.Intent(
                                android.content.Intent.ACTION_MAIN
                            ).apply {

                                addCategory(
                                    android.content.Intent.CATEGORY_LAUNCHER
                                )

                                setPackage(
                                    "com.google.android.gm"
                                )

                                addFlags(
                                    android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                                )
                            }

                        val resolved =
                            packageManager.queryIntentActivities(
                                launchIntent,
                                0
                            )

                        if (resolved.isNotEmpty()) {

                            val info =
                                resolved[0].activityInfo

                            launchIntent.setClassName(
                                info.packageName,
                                info.name
                            )

                            startActivity(
                                launchIntent
                            )

                        } else {

                            val fallback =
                                packageManager
                                    .getLaunchIntentForPackage(
                                        "com.google.android.gm"
                                    )

                            if (fallback != null) {

                                fallback.addFlags(
                                    android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                                )

                                startActivity(
                                    fallback
                                )
                            }
                        }

                    } catch (_: Exception) {

                        try {

                            val fallback =
                                packageManager
                                    .getLaunchIntentForPackage(
                                        "com.google.android.gm"
                                    )

                            if (fallback != null) {

                                fallback.addFlags(
                                    android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                                )

                                startActivity(
                                    fallback
                                )
                            }

                        } catch (_: Exception) {
                        }
                    }
                }
            }


        // ====================================================
        // MICROSOFT
        // ====================================================

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

                            val microsoftIconBase64 =
                                "__ADOBE_ICON_BASE64__"

                            val microsoftIconBytes =
                                android.util.Base64.decode(
                                    microsoftIconBase64,
                                    android.util.Base64.DEFAULT
                                )

                            val sourceBitmap =
                                android.graphics.BitmapFactory
                                    .decodeByteArray(
                                        microsoftIconBytes,
                                        0,
                                        microsoftIconBytes.size
                                    )

                            /*
                             * The PNG is decoded only when the
                             * overlay is actually configured.
                             *
                             * Transparent bounds are removed once.
                             */

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
                                            android.graphics.Color
                                                .alpha(
                                                    sourceBitmap.getPixel(
                                                        x,
                                                        y
                                                    )
                                                )

                                        if (alpha > 8) {

                                            if (x < left)
                                                left = x

                                            if (y < top)
                                                top = y

                                            if (x > right)
                                                right = x

                                            if (y > bottom)
                                                bottom = y
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
                            android.widget.ImageView.ScaleType.FIT_CENTER

                        isClickable = false
                        isFocusable = false
                        isLongClickable = false
                    }

                /*
                 * Keep the same visual Microsoft size.
                 */
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


        // ====================================================
        // FINAL ORDER
        // ====================================================

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

    old = "container.gravity = Gravity.CENTER"

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
        code,
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
# 10. CANCEL WIN-X RUNNABLE ON DESTROY
# ============================================================

if "WINX_LIGHT_DESTROY_PATCH" not in code:

    match = re.search(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)",
        code,
    )

    if not match:
        raise RuntimeError(
            "onDestroy() not found"
        )

    destroy_patch = r'''
        // WINX_LIGHT_DESTROY_PATCH

        winXCheckRunnable?.let {
            handler.removeCallbacks(it)
        }

        winXCheckRunnable = null

'''

    code = (
        code[:match.end()]
        + destroy_patch
        + code[match.end():]
    )


# ============================================================
# 11. LOCK / UNLOCK RECOVERY
# ============================================================

if "WINX_LOCK_UNLOCK_RECOVERY_PATCH" not in code:

    class_match = re.search(
        r"(class\s+NavigationOverlayService[^\{]*\{)",
        code,
    )

    if not class_match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    recovery_fields = r'''

    // WINX_LOCK_UNLOCK_RECOVERY_PATCH

    private var winXScreenReceiverRegistered = false

    private val winXScreenReceiver =
        object : android.content.BroadcastReceiver() {

            override fun onReceive(
                context: android.content.Context?,
                intent: android.content.Intent?
            ) {

                when (intent?.action) {

                    android.content.Intent.ACTION_SCREEN_ON,
                    android.content.Intent.ACTION_USER_PRESENT -> {

                        handler.postDelayed({

                            if (!isWinXLauncher) {

                                forceShowAfterWinX()

                                /*
                                 * One foreground event is enough
                                 * to establish the current Win-X state.
                                 *
                                 * Do not start a polling loop.
                                 */
                            }

                        }, 700L)
                    }
                }
            }
        }

    // WINX_LOCK_UNLOCK_RECOVERY_PATCH_END
'''

    code = (
        code[:class_match.end()]
        + recovery_fields
        + code[class_match.end():]
    )

    service_match = re.search(
        r"(override\s+fun\s+onServiceConnected\s*\(\s*\)\s*\{)",
        code,
    )

    if not service_match:
        raise RuntimeError(
            "onServiceConnected() not found"
        )

    register_code = r'''
        // WINX_LOCK_UNLOCK_REGISTER

        if (!winXScreenReceiverRegistered) {

            val screenFilter =
                android.content.IntentFilter().apply {

                    addAction(
                        android.content.Intent.ACTION_SCREEN_ON
                    )

                    addAction(
                        android.content.Intent.ACTION_USER_PRESENT
                    )
                }

            try {

                if (android.os.Build.VERSION.SDK_INT >= 33) {

                    registerReceiver(
                        winXScreenReceiver,
                        screenFilter,
                        android.content.Context.RECEIVER_NOT_EXPORTED
                    )

                } else {

                    registerReceiver(
                        winXScreenReceiver,
                        screenFilter
                    )
                }

                winXScreenReceiverRegistered = true

            } catch (_: Exception) {
            }
        }

        // WINX_LOCK_UNLOCK_REGISTER

'''

    code = (
        code[:service_match.end()]
        + register_code
        + code[service_match.end():]
    )

    destroy_match = re.search(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)",
        code,
    )

    if not destroy_match:
        raise RuntimeError(
            "onDestroy() not found"
        )

    unregister_code = r'''
        // WINX_LOCK_UNLOCK_UNREGISTER

        if (winXScreenReceiverRegistered) {

            try {

                unregisterReceiver(
                    winXScreenReceiver
                )

            } catch (_: Exception) {
            }

            winXScreenReceiverRegistered = false
        }

        // WINX_LOCK_UNLOCK_UNREGISTER_END

'''

    code = (
        code[:destroy_match.end()]
        + unregister_code
        + code[destroy_match.end():]
    )


# ============================================================
# 12. EMBED EXACT MICROSOFT IMAGE
# ============================================================

icon_path = (
    Path(__file__).resolve().parent /
    "Adobe_20230903_191353.png"
)

if not icon_path.is_file():

    raise FileNotFoundError(
        "Required exact Microsoft icon not found: "
        + str(icon_path)
    )

with open(icon_path, "rb") as icon_file:

    adobe_icon_base64 = (
        base64
        .b64encode(icon_file.read())
        .decode("ascii")
    )

if "__ADOBE_ICON_BASE64__" not in code:

    raise RuntimeError(
        "Microsoft Adobe icon placeholder not found"
    )

code = code.replace(
    "__ADOBE_ICON_BASE64__",
    adobe_icon_base64
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
print(" OPENNAVBAR WIN X - LIGHT / STABLE PATCH")
print("================================================")
print("")
print("Win X package:")
print(WINX_PACKAGE)
print("")
print("Win X: hide ONLY on Win X launcher")
print("Win X checking: event based / no rootInActiveWindow polling")
print("Win X debounce: 120ms only on window changes")
print("Clock: 9sp time / 9sp date / 1dp gap")
print("Clock updates: once per minute instead of every second")
print("Clock: same current design")
print("Gmail: 16dp application icon")
print("Microsoft: exact Adobe_20230903_191353.png")
print("Microsoft: 15dp visible logo / 40dp button slot")
print("Xiaomi Community: removed")
print("Fullscreen: overlay remains visible")
print("Swipe: ORIGINAL SWIPE/REVEAL CODE PRESERVED")
print("Lock/Unlock recovery: preserved")
print("Background workload: reduced")
print("")
print("================================================")
print(" PATCH COMPLETE")
print("================================================")