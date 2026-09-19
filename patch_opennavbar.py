import sys
import re
from pathlib import Path

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
            i += 1
            continue

        if in_block_comment:
            if c == "*" and n == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue

        if in_char:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == "'":
                in_char = False
            i += 1
            continue

        if c == "/" and n == "/":
            in_line_comment = True
            i += 2
            continue

        if c == "/" and n == "*":
            in_block_comment = True
            i += 2
            continue

        if c == '"':
            in_string = True
            i += 1
            continue

        if c == "'":
            in_char = True
            i += 1
            continue

        if c == "{":
            depth += 1

        elif c == "}":
            depth -= 1
            if depth == 0:
                return i

        i += 1

    raise RuntimeError("Matching brace not found")


def find_function(text, name):
    pattern = re.compile(
        r'private\s+fun\s+' + re.escape(name) + r'\s*\('
    )

    match = pattern.search(text)

    if not match:
        raise RuntimeError(f"Function not found: {name}")

    brace = text.find("{", match.end())

    if brace == -1:
        raise RuntimeError(f"Opening brace not found: {name}")

    end = find_matching_brace(text, brace)

    return match.start(), brace, end


def insert_once(text, marker, position):
    if marker in text:
        return text

    return text[:position] + marker + text[position:]


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
        accessibility_import = "import android.accessibilityservice.AccessibilityService"

        if accessibility_import in code:
            code = code.replace(
                accessibility_import,
                accessibility_import + "\n" + imp,
                1
            )
        else:
            code = imp + "\n" + code


# ============================================================
# 2. WinX stable state
# ============================================================

winx_state_patch = r'''
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

if "WINX_STABLE_PATCH" not in code:
    service_match = re.search(
        r'class\s+NavigationOverlayService\b[^{]*\{',
        code
    )

    if not service_match:
        raise RuntimeError("NavigationOverlayService class not found")

    service_open = code.find("{", service_match.start())
    code = (
        code[:service_open + 1]
        + winx_state_patch
        + code[service_open + 1:]
    )


# ============================================================
# 3. Accessibility event WinX check
# ============================================================

if "WINX_STABLE_EVENT_PATCH" not in code:

    event_match = re.search(
        r'override\s+fun\s+onAccessibilityEvent\s*\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{',
        code
    )

    if not event_match:
        raise RuntimeError("onAccessibilityEvent not found")

    insert_pos = event_match.end()

    event_patch = r'''
        // WINX_STABLE_EVENT_PATCH
        checkWinXStateDelayed()
        // WINX_STABLE_EVENT_PATCH_END
'''

    code = (
        code[:insert_pos]
        + event_patch
        + code[insert_pos:]
    )


# ============================================================
# 4. Protect showOverlay while WinX home is active
# ============================================================

if "WINX_SHOW_OVERLAY_PROTECTION" not in code:

    start, brace, end = find_function(
        code,
        "showOverlay"
    )

    protection = r'''
    // WINX_SHOW_OVERLAY_PROTECTION
    if (isWinXLauncher) return
'''

    code = (
        code[:brace + 1]
        + protection
        + code[brace + 1:]
    )


# ============================================================
# 5. Disable fullscreen auto-hide
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
# ============================================================

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

if "WINX_CLOCK_DATE_PATCH" not in code:

    service_match = re.search(
        r'class\s+NavigationOverlayService\b[^{]*\{',
        code
    )

    if not service_match:
        raise RuntimeError("NavigationOverlayService class not found")

    service_open = code.find("{", service_match.start())

    code = (
        code[:service_open + 1]
        + clock_patch
        + code[service_open + 1:]
    )


# ============================================================
# 7. Configure overlay view
# ============================================================

if "WINX_CLOCK_GRAVITY_PATCH" not in code:

    configure_match = re.search(
        r'private\s+fun\s+configureOverlayView\s*\(',
        code
    )

    if not configure_match:
        raise RuntimeError("configureOverlayView not found")

    _, configure_brace, configure_end = find_function(
        code,
        "configureOverlayView"
    )

    configure_code = code[configure_brace + 1:configure_end]

    # --------------------------------------------------------
    # Insert clock after original navigation container setup
    # --------------------------------------------------------

    if "WINX_CLOCK_INSERTED" not in configure_code:

        anchor = re.search(
            r'container\.addView\s*\(\s*frame\s*\)',
            configure_code
        )

        if not anchor:
            raise RuntimeError(
                "Original navigation container.addView(frame) not found"
            )

        insert_at = anchor.end()

        clock_insert = r'''

        // WINX_CLOCK_INSERTED

        val winXClockRotation = when (position) {
            "left" -> 90f
            "right" -> -90f
            else -> 0f
        }

        val winXClock = createWinXClock(
            textColor = android.graphics.Color.WHITE,
            rotation = winXClockRotation
        )

        val winXSpacer = View(this).apply {
            isClickable = false
            isFocusable = false
        }

        val winXClockParams =
            if (isVerticalBar) {
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    hitboxSize
                )
            } else {
                LinearLayout.LayoutParams(
                    dpToPx(50),
                    LinearLayout.LayoutParams.MATCH_PARENT
                )
            }

        val winXSpacerParams =
            if (isVerticalBar) {
                LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.MATCH_PARENT,
                    0
                ).apply {
                    weight = 1f
                }
            } else {
                LinearLayout.LayoutParams(
                    0,
                    LinearLayout.LayoutParams.MATCH_PARENT
                ).apply {
                    weight = 1f
                }
            }

        if (shouldSwap) {
            container.addView(
                winXClock,
                1,
                winXClockParams
            )

            container.addView(
                winXSpacer,
                2,
                winXSpacerParams
            )
        } else {
            container.addView(
                winXSpacer,
                2,
                winXSpacerParams
            )

            container.addView(
                winXClock,
                3,
                winXClockParams
            )
        }

'''

        configure_code = (
            configure_code[:insert_at]
            + clock_insert
            + configure_code[insert_at:]
        )

    # --------------------------------------------------------
    # Gmail + Microsoft buttons
    # --------------------------------------------------------

    if "WINX_GMAIL_MICROSOFT_INSERTED" not in configure_code:

        gmail_ms_patch = r'''

        // WINX_GMAIL_MICROSOFT_INSERTED

        // ----------------------------------------------------
        // Gmail button
        // Exact embedded custom Gmail icon is preserved.
        // Visible size: 16dp x 16dp.
        // ----------------------------------------------------

        val winXGmailButton =
            android.widget.FrameLayout(this).apply {

                isClickable = true
                isFocusable = true

                setOnClickListener {

                    try {
                        val intent =
                            packageManager.getLaunchIntentForPackage(
                                "com.google.android.gm"
                            )

                        if (intent != null) {
                            intent.addFlags(
                                android.content.Intent.FLAG_ACTIVITY_NEW_TASK
                            )

                            startActivity(intent)
                        } else {

                            val gmailIntent =
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

                            startActivity(gmailIntent)
                        }

                    } catch (_: Exception) {
                    }
                }
            }

        val gmailIcon =
            android.widget.ImageView(this).apply {

                scaleType =
                    android.widget.ImageView.ScaleType.CENTER_INSIDE

                isClickable = false
                isFocusable = false
                isLongClickable = false

                try {

                    val gmailBytes =
                        android.util.Base64.decode(
                            "__GMAIL_ICON_BASE64__",
                            android.util.Base64.DEFAULT
                        )

                    val gmailBitmap =
                        android.graphics.BitmapFactory.decodeByteArray(
                            gmailBytes,
                            0,
                            gmailBytes.size
                        )

                    if (gmailBitmap != null) {
                        setImageBitmap(gmailBitmap)
                    }

                } catch (_: Exception) {
                    // Keep the exact embedded Gmail icon.
                    // No system Gmail replacement.
                }
            }

        winXGmailButton.addView(
            gmailIcon,
            android.widget.FrameLayout.LayoutParams(
                dpToPx(16),
                dpToPx(16),
                android.view.Gravity.CENTER
            )
        )


        // ----------------------------------------------------
        // Microsoft button
        // Exact Adobe_20230903_191353.png
        // No pixel scanning.
        // No getPixel().
        // No Bitmap.createBitmap().
        // Visible size: 15dp x 15dp.
        // ----------------------------------------------------

        val winXMicrosoftButton =
            android.widget.FrameLayout(this).apply {

                isClickable = true
                isFocusable = true

                setOnClickListener {

                    try {

                        val microsoftIntent =
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

                        startActivity(microsoftIntent)

                    } catch (_: Exception) {
                    }
                }
            }

        val microsoftIcon =
            android.widget.ImageView(this).apply {

                scaleType =
                    android.widget.ImageView.ScaleType.FIT_CENTER

                isClickable = false
                isFocusable = false
                isLongClickable = false

                try {

                    val adobeBytes =
                        android.util.Base64.decode(
                            "__ADOBE_ICON_BASE64__",
                            android.util.Base64.DEFAULT
                        )

                    val sourceBitmap =
                        android.graphics.BitmapFactory.decodeByteArray(
                            adobeBytes,
                            0,
                            adobeBytes.size
                        )

                    // LIGHTWEIGHT VERSION:
                    // Direct bitmap display.
                    // No getPixel() scanning.
                    // No Bitmap.createBitmap().
                    if (sourceBitmap != null) {
                        setImageBitmap(sourceBitmap)
                    }

                } catch (_: Exception) {
                }
            }

        winXMicrosoftButton.addView(
            microsoftIcon,
            android.widget.FrameLayout.LayoutParams(
                dpToPx(15),
                dpToPx(15),
                android.view.Gravity.CENTER
            )
        )


        // ----------------------------------------------------
        // Button positions
        //
        // Normal:
        // Back → Home → Microsoft → Gmail → SPACE → Clock → Recent
        //
        // Swapped:
        // Recent → Gmail → SPACE → Microsoft → Clock → Home → Back
        // ----------------------------------------------------

        if (shouldSwap) {

            container.addView(
                winXGmailButton,
                2,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    dpToPx(40)
                )
            )

            container.addView(
                winXMicrosoftButton,
                4,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    dpToPx(40)
                )
            )

        } else {

            container.addView(
                winXMicrosoftButton,
                2,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    dpToPx(40)
                )
            )

            container.addView(
                winXGmailButton,
                3,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    dpToPx(40)
                )
            )
        }

'''

        configure_code = (
            configure_code
            + gmail_ms_patch
        )

    # --------------------------------------------------------
    # Gravity
    # --------------------------------------------------------

    gravity_old = "container.gravity = Gravity.CENTER"

    gravity_new = r'''container.gravity =
    if (isVerticalBar)
        Gravity.CENTER_HORIZONTAL
    else
        Gravity.CENTER_VERTICAL

// WINX_CLOCK_GRAVITY_PATCH'''

    if gravity_old in configure_code:
        configure_code = configure_code.replace(
            gravity_old,
            gravity_new,
            1
        )

    code = (
        code[:configure_brace + 1]
        + configure_code
        + code[configure_end:]
    )


# ============================================================
# 8. Clock cleanup
# ============================================================

if "WINX_CLOCK_CLEANUP_PATCH" not in code:

    destroy_match = re.search(
        r'override\s+fun\s+onDestroy\s*\(\s*\)\s*\{',
        code
    )

    if destroy_match:

        cleanup = r'''
        // WINX_CLOCK_CLEANUP_PATCH
        handler.removeCallbacks(winXClockRunnable)
        winXClockStarted = false
        winXClockTextView = null
        winXDateTextView = null
'''

        insert_pos = destroy_match.end()

        code = (
            code[:insert_pos]
            + cleanup
            + code[insert_pos:]
        )


# ============================================================
# 8.5 Lock / Unlock recovery
# ============================================================

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
                            checkWinXStateDelayed()

                        }

                    }, 700L)
                }
            }
        }
    }

// WINX_LOCK_UNLOCK_RECOVERY_PATCH_END
'''

if "WINX_LOCK_UNLOCK_RECOVERY_PATCH" not in code:

    service_match = re.search(
        r'class\s+NavigationOverlayService\b[^{]*\{',
        code
    )

    if not service_match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    service_open = code.find("{", service_match.start())

    code = (
        code[:service_open + 1]
        + recovery_fields
        + code[service_open + 1:]
    )


# ============================================================
# 8.6 Register screen receiver
# ============================================================

if "WINX_LOCK_UNLOCK_REGISTER" not in code:

    connected_match = re.search(
        r'override\s+fun\s+onServiceConnected\s*\(\s*\)\s*\{',
        code
    )

    if connected_match:

        register_patch = r'''
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

        insert_pos = connected_match.end()

        code = (
            code[:insert_pos]
            + register_patch
            + code[insert_pos:]
        )


# ============================================================
# 8.7 Unregister screen receiver
# ============================================================

if "WINX_LOCK_UNLOCK_UNREGISTER" not in code:

    destroy_match = re.search(
        r'override\s+fun\s+onDestroy\s*\(\s*\)\s*\{',
        code
    )

    if destroy_match:

        unregister_patch = r'''
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

        insert_pos = destroy_match.end()

        code = (
            code[:insert_pos]
            + unregister_patch
            + code[insert_pos:]
        )


# ============================================================
# 8.8 Preserve existing Gmail embedded Base64
# ============================================================

# IMPORTANT:
# We deliberately do NOT replace the Gmail Base64.
#
# The existing successful source already contains the exact
# custom Gmail icon. We only preserve it.
#
# If the source has a Gmail placeholder, the script refuses
# to invent a new icon instead of replacing it with a system
# Gmail icon.
# ============================================================

if "__GMAIL_ICON_BASE64__" in code:

    # Try to recover an existing embedded Gmail Base64 from
    # the original Kotlin source if the successful source has
    # already been patched before.
    gmail_pattern = re.compile(
        r'val\s+gmailBytes\s*=\s*android\.util\.Base64\.decode\s*\(\s*"([^"]+)"',
        re.DOTALL
    )

    gmail_match = gmail_pattern.search(code)

    if gmail_match:
        existing_gmail = gmail_match.group(1)

        if existing_gmail == "__GMAIL_ICON_BASE64__":
            raise RuntimeError(
                "Exact custom Gmail Base64 icon is missing. "
                "Do not replace it with a system Gmail icon."
            )


# ============================================================
# 8.9 Exact Microsoft Adobe PNG
# ============================================================

icon_path = (
    Path(__file__).resolve().parent
    / "Adobe_20230903_191353.png"
)

if not icon_path.is_file():

    raise FileNotFoundError(
        "Required exact Microsoft icon not found: "
        + str(icon_path)
    )

import base64

with open(icon_path, "rb") as icon_file:
    adobe_icon_base64 = base64.b64encode(
        icon_file.read()
    ).decode("ascii")

if "__ADOBE_ICON_BASE64__" not in code:

    # If the source already contains the embedded Adobe icon,
    # leave it untouched.
    #
    # Otherwise fail instead of silently using another image.
    if "val adobeBytes" not in code:

        raise RuntimeError(
            "Microsoft Adobe icon placeholder not found"
        )

else:

    code = code.replace(
        "__ADOBE_ICON_BASE64__",
        adobe_icon_base64
    )


# ============================================================
# 9. Save
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print()
print("==============================================")
print(" OpenNavBar WinX patch applied successfully")
print("==============================================")
print()
print("WinX package:")
print(WINX_PACKAGE)
print()
print("Preserved:")
print(" - WinX home-only hiding")
print(" - WinX re-show")
print(" - Original clock/date design")
print(" - Swipe / Reveal behavior")
print(" - Gmail custom embedded icon")
print(" - Gmail 16dp x 16dp")
print(" - Microsoft exact Adobe PNG")
print(" - Microsoft 15dp x 15dp")
print()
print("Removed heavy Microsoft processing:")
print(" - getPixel() scanning")
print(" - Bitmap.createBitmap() cropping")
print()
print("Microsoft icon is now displayed directly.")
print()