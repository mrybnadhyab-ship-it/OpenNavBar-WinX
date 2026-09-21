ayoutParams(
                    dpToPx(40),
                    dpToPx(40),
                    0f
                )
            )
            container.addView(
                winXGmailButton,
                3,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    dpToPx(40),
                    0f
                )
            )
            container.addView(
                winXShowHiddenButton,
                5,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    dpToPx(40),
                    0f
                )
            )
            container.addView(
                winXSearchButton,
                1,
                LinearLayout.LayoutParams(
                    dpToPx(40),
                    dpToPx(40),
                    0f
                )
            )
        // WINX_SHOW_HIDDEN_ICONS_PATCH_END
        }
        // WINX_GMAIL_POSITION_PATCH_END

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
        // WINX_OVERLAY_HEALTH_CLEANUP
        winXOverlayHealthRunnable?.let {
            handler.removeCallbacks(it)
        }
        winXOverlayHealthRunnable = null
        winXOverlayHealthRecoveryRunning = false

        // WINX_STATE_MONITOR_CLEANUP
        winXCheckRunnable?.let {
            handler.removeCallbacks(it)
        }
        winXCheckRunnable = null
        cancelWinXRestartGrace()
        // WINX_STATE_MONITOR_CLEANUP_END
        // WINX_OVERLAY_HEALTH_CLEANUP

        // WINX_CLOCK_CLEANUP_PATCH
        handler.removeCallbacks(winXClockRunnable)
        winXClockStarted = false
        winXClockTextView = null
        winXDateTextView = null

'''
        code = code[:match.end()] + cleanup + code[match.end():]


# ============================================================
# 8.5. LOCK / UNLOCK RECOVERY ONLY
#      Restore the overlay after the screen is unlocked.
#      Do not change Win-X, fullscreen, Gmail, clock/date, or Swipe/Reveal.
# ============================================================

if "WINX_LOCK_UNLOCK_RECOVERY_PATCH" not in code:
    class_match = re.search(
        r"(class\s+NavigationOverlayService[^\{]*\{)",
        code,
    )
    if not class_match:
        raise RuntimeError("NavigationOverlayService class not found")

    recovery_fields = r'''

    // WINX_LOCK_UNLOCK_RECOVERY_PATCH
    private var winXScreenReceiverRegistered = false

    private val winXScreenReceiver = object : android.content.BroadcastReceiver() {
        override fun onReceive(
            context: android.content.Context?,
            intent: android.content.Intent?
        ) {
            when (intent?.action) {
                android.content.Intent.ACTION_SCREEN_OFF -> {
                    // Lock screen / display-off: hide immediately and do not
                    // attempt to restore until the user has actually unlocked.
                    hideWinXOverlayForLockScreen()
                }
                android.content.Intent.ACTION_SCREEN_ON -> {
                    // SCREEN_ON can occur while the keyguard is still visible.
                    // Do not show OpenNavBar here.
                    handler.postDelayed({
                        if (isWinXLockScreenActive()) {
                            hideWinXOverlayForLockScreen()
                        }
                    }, 150L)
                }
                android.content.Intent.ACTION_USER_PRESENT -> {
                    // USER_PRESENT means the device has actually been unlocked.
                    handler.postDelayed({
                        if (!isWinXLockScreenActive() && !isWinXLauncher) {
                            forceShowAfterWinX()
                            checkWinXStateDelayed()
                        }
                    }, 250L)
                }
            }
        }
    }
    // WINX_LOCK_UNLOCK_RECOVERY_PATCH_END
'''

    code = code[:class_match.end()] + recovery_fields + code[class_match.end():]

    service_match = re.search(
        r"(override\s+fun\s+onServiceConnected\s*\(\s*\)\s*\{)",
        code,
    )
    if not service_match:
        raise RuntimeError("onServiceConnected() not found")

    register_code = r'''
        // WINX_LOCK_UNLOCK_REGISTER
        if (!winXScreenReceiverRegistered) {
            val screenFilter = android.content.IntentFilter().apply {
                addAction(android.content.Intent.ACTION_SCREEN_OFF)
                addAction(android.content.Intent.ACTION_SCREEN_ON)
                addAction(android.content.Intent.ACTION_USER_PRESENT)
            }

            try {
                if (android.os.Build.VERSION.SDK_INT >= 33) {
                    registerReceiver(
                        winXScreenReceiver,
                        screenFilter,
                        android.content.Context.RECEIVER_NOT_EXPORTED
                    )
                } else {
                    registerReceiver(winXScreenReceiver, screenFilter)
                }
                winXScreenReceiverRegistered = true
            } catch (_: Exception) {
            }
        }
        // WINX_LOCK_UNLOCK_REGISTER

        // WINX_OVERLAY_HEALTH_CONNECTED
        scheduleWinXOverlayHealthCheck(500L)
        // WINX_OVERLAY_HEALTH_CONNECTED

'''
    code = code[:service_match.end()] + register_code + code[service_match.end():]

    destroy_match = re.search(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)",
        code,
    )
    if not destroy_match:
        raise RuntimeError("onDestroy() not found")

    unregister_code = r'''
        // WINX_LOCK_UNLOCK_UNREGISTER
        if (winXScreenReceiverRegistered) {
            try {
                unregisterReceiver(winXScreenReceiver)
            } catch (_: Exception) {
            }
            winXScreenReceiverRegistered = false
        }
        // WINX_LOCK_UNLOCK_UNREGISTER_END

'''
    code = code[:destroy_match.end()] + unregister_code + code[destroy_match.end():]

# ============================================================
# 8.9. COPY THE EXACT ADOBE IMAGE
#      Gmail is NOT touched.
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

import shutil

project_root = (
    Path(__file__).resolve().parent
    / "opennavbar"
)

drawable_dir = (
    project_root
    / "app"
    / "src"
    / "main"
    / "res"
    / "drawable-nodpi"
)

drawable_dir.mkdir(
    parents=True,
    exist_ok=True
)

microsoft_drawable = (
    drawable_dir
    / "microsoft_adobe.png"
)

shutil.copyfile(
    icon_path,
    microsoft_drawable
)


# ============================================================
# 8.95. WINDOWS 10 SHOW-HIDDEN-ICONS CHEVRON
#      Windows 10 style: simple thin white upward caret (^)
#      16dp visual inside the existing 40dp button slot.
# ============================================================

show_hidden_vector = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="16dp"
    android:height="16dp"
    android:viewportWidth="16"
    android:viewportHeight="16">

    <path
        android:fillColor="@android:color/transparent"
        android:strokeColor="#FFFFFFFF"
        android:strokeWidth="1.6"
        android:strokeLineCap="square"
        android:strokeLineJoin="miter"
        android:pathData="M3.0,9.5 L8.0,4.5 L13.0,9.5" />

</vector>
"""

show_hidden_drawable = drawable_dir / "winx_show_hidden.xml"
show_hidden_drawable.write_text(
    show_hidden_vector,
    encoding="utf-8"
)

# ============================================================
# 8.96. WINDOWS 10 SEARCH ICON
#      18dp magnifying glass, with the handle pointing down-left
#      like the reference image. The button slot remains 40dp.
# ============================================================

search_vector = """<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="16dp"
    android:height="16dp"
    android:viewportWidth="18"
    android:viewportHeight="18">

    <path
        android:fillColor="@android:color/transparent"
        android:strokeColor="#FFFFFFFF"
        android:strokeWidth="1.7"
        android:strokeLineCap="square"
        android:strokeLineJoin="miter"
        android:pathData="M7.4,2.6 A4.8,4.8 0,1 0,7.4,12.2 A4.8,4.8 0,1 0,7.4,2.6 M3.8,10.9 L0.2,14.5" />

</vector>
"""

search_drawable = drawable_dir / "winx_search.xml"
search_drawable.write_text(
    search_vector,
    encoding="utf-8"
)

# ============================================================
# 9. SAVE
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)

print("================================================")
print(" OPENNAVBAR WIN X + CLOCK + LOCK SCREEN FIX")
print("================================================")
print("")
print("Win X package:")
print(WINX_PACKAGE)
print("")
print("Win X: hide only on Win X launcher")
print("Clock: 9sp time / 9sp date / group rotation / 1dp gap / non-touch")
print("Gmail: custom supplied icon / 16dp")
print("Gmail: 16dp icon / beside Home on clock side")
print("Xiaomi Community: removed")
print("Microsoft: EXACT Adobe_20230903_191353.png / 20dp visible logo / overlay health recovery / Windows-style 40dp button slots")
print("Search: Windows 10-style magnifying glass / between Back and Home / 40dp button slot")
print("Lock screen: OpenNavBar hidden until USER_PRESENT / real unlock")
print("Swipe: ORIGINAL SWIPE/REVEAL CODE PRESERVED")
print("================================================")
print("PATCH COMPLETE")
print("================================================")
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
    // WINX_OVERLAY_HEALTH_PATCH

    private var winXOverlayHealthRunnable: Runnable? = null
    private var winXOverlayHealthRecoveryRunning = false

    private fun scheduleWinXOverlayHealthCheck(delayMs: Long = 350L) {
        if (isWinXLauncher) return

        winXOverlayHealthRunnable?.let {
            handler.removeCallbacks(it)
        }

        winXOverlayHealthRunnable = Runnable {
            if (isWinXLauncher || winXOverlayHealthRecoveryRunning) return@Runnable

            val view = overlayView
            val windowAttached = try {
                view != null && view.windowToken != null
            } catch (_: Exception) {
                false
            }

            // Match Navigation Bar v3.3.0's important recovery rule:
            // a missing window token means the overlay was detached.
            // Do NOT use visibility here, because normal auto-hide is valid.
            if (!windowAttached) {
                winXOverlayHealthRecoveryRunning = true

                try {
                    hideOverlay()
                } catch (_: Exception) {
                }

                handler.postDelayed({
                    try {
                        if (!isWinXLauncher) {
                            showOverlay()
                        }
                    } catch (_: Exception) {
                    }
                    winXOverlayHealthRecoveryRunning = false
                }, 180L)
            }
        }

        handler.postDelayed(winXOverlayHealthRunnable!!, delayMs)
    }

    // WINX_OVERLAY_HEALTH_PATCH_END


    private var isWinXLauncher = false
    private var winXCheckRunnable: Runnable? = null
    private var winXRestartGraceRunnable: Runnable? = null
    private var winXRestartGraceActive = false

    private fun cancelWinXRestartGrace() {
        winXRestartGraceRunnable?.let {
            handler.removeCallbacks(it)
        }
        winXRestartGraceRunnable = null
        winXRestartGraceActive = false
    }

    private fun startWinXRestartGrace() {
        if (winXRestartGraceActive) return

        winXRestartGraceActive = true

        // Win-X can temporarily disappear while restarting. Keep OpenNavBar
        // alive and visible for up to 15 seconds. If Win-X returns earlier,
        // the next state check cancels this timer and hides the bar again.
        winXRestartGraceRunnable = Runnable {
            winXRestartGraceRunnable = null
            winXRestartGraceActive = false

            try {
                val currentPackage = getCurrentForegroundPackage()
                if (currentPackage != "com.InternityLabs.Launcher.WinX") {
                    isWinXLauncher = false
                    forceShowAfterWinX()
                }
            } catch (_: Exception) {
                isWinXLauncher = false
                try {
                    forceShowAfterWinX()
                } catch (_: Exception) {
                }
            }
        }

        handler.postDelayed(winXRestartGraceRunnable!!, 15000L)
    }

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
            try {
                // WINX_LOCK_SCREEN_STATE_GUARD
                if (isWinXLockScreenActive()) {
                    hideWinXOverlayForLockScreen()
                    handler.postDelayed({
                        checkWinXStateDelayed()
                    }, 750L)
                    return@Runnable
                }

                val currentPackage = getCurrentForegroundPackage()

                when {
                    // Win-X is definitely back in the foreground.
                    currentPackage == "com.InternityLabs.Launcher.WinX" -> {
                        cancelWinXRestartGrace()

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
                    }

                    // Empty/unknown package is the important case during a
                    // Win-X restart. Do NOT treat it as a real exit.
                    // Show/keep the bar alive and give Win-X up to 15 seconds
                    // to come back.
                    currentPackage.isEmpty() -> {
                        isWinXLauncher = false
                        startWinXRestartGrace()

                        if (overlayView?.windowToken != null &&
                            overlayView?.visibility != View.VISIBLE
                        ) {
                            forceShowAfterWinX()
                        }
                    }

                    // A definite other package means the user really left
                    // Win-X. Cancel any restart grace and keep the bar shown.
                    else -> {
                        cancelWinXRestartGrace()

                        if (isWinXLauncher) {
                            isWinXLauncher = false
                            forceShowAfterWinX()
                        }
                    }
                }
            } catch (_: Exception) {
                // Never let a temporary Win-X restart kill OpenNavBar.
            }

            // Keep checking independently of AccessibilityEvents because
            // Win-X may restart without producing a useful event.
            handler.postDelayed({
                checkWinXStateDelayed()
            }, 750L)
        }

        handler.postDelayed(winXCheckRunnable!!, 250L)
    }

    private fun forceShowAfterWinX() {
        // WINX_FORCE_SHOW_LOCK_GUARD
        if (isWinXLockScreenActive()) {
            hideWinXOverlayForLockScreen()
            return
        }

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


    // WINX_LOCK_SCREEN_GUARD_PATCH
    // Never allow OpenNavBar to be visible while the Android keyguard/lock
    // screen is active. This is intentionally independent of Win-X state.
    private fun isWinXLockScreenActive(): Boolean {
        return try {
            val keyguardManager =
                getSystemService(android.content.Context.KEYGUARD_SERVICE)
                    as? android.app.KeyguardManager
            keyguardManager?.isKeyguardLocked == true
        } catch (_: Exception) {
            false
        }
    }

    private fun hideWinXOverlayForLockScreen() {
        try {
            winXOverlayHealthRunnable?.let {
                handler.removeCallbacks(it)
            }
            autoHideRunnable?.let {
                handler.removeCallbacks(it)
            }
            overlayView?.animate()?.cancel()
            overlayView?.visibility = View.GONE
            overlayView?.alpha = 0f
        } catch (_: Exception) {
        }
    }
    // WINX_LOCK_SCREEN_GUARD_PATCH_END
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
        // WINX_LOCK_SCREEN_EVENT_GUARD
        if (isWinXLockScreenActive()) {
            hideWinXOverlayForLockScreen()
            return
        }

        checkWinXStateDelayed()
        scheduleWinXOverlayHealthCheck()

        // WINX_VIDEO_ROTATION_RECOVERY
        // Video/fullscreen transitions can temporarily detach the overlay
        // (especially after portrait playback). Once the window transition
        // finishes, restore the bar automatically instead of requiring a
        // manual swipe/reveal. Win-X remains the only screen where the bar
        // is intentionally hidden.
        if (event != null &&
            event.eventType == android.view.accessibility.AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            handler.postDelayed({
                try {
                    val currentPackageAfterTransition = getCurrentForegroundPackage()
                    if (currentPackageAfterTransition != "com.InternityLabs.Launcher.WinX" &&
                        currentPackageAfterTransition.isNotEmpty() &&
                        !isWinXLauncher) {
                        forceShowAfterWinX()
                        scheduleWinXOverlayHealthCheck(250L)
                    }
                } catch (_: Exception) {
                }
            }, 700L)
        }
        // WINX_VIDEO_ROTATION_RECOVERY_END

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

        // WINX_LOCK_SCREEN_SHOW_GUARD
        if (isWinXLockScreenActive()) {
            hideWinXOverlayForLockScreen()
            return
        }

'''
    code = code[:match.end()] + protection + code[match.end():]


# ============================================================
# 4.5. KEEP OVERLAY VISIBLE IN FULLSCREEN
#      Only disable the existing fullscreen auto-hide condition.
#      Do not change Win-X, clock/date, Gmail, or Swipe/Reveal.
# ============================================================

if "WINX_FULLSCREEN_STABLE_PATCH" not in code:
    fullscreen_expr = 'prefs.getBoolean("hide_on_fullscreen", true)'
    fullscreen_replacement = 'false /* WINX_FULLSCREEN_STABLE_PATCH */'

    if fullscreen_expr in code:
        code = code.replace(fullscreen_expr, fullscreen_replacement, 1)
    else:
        raise RuntimeError("hide_on_fullscreen preference not found")


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

    // WINX_SHARED_SPACE_SIZE_PATCH
    // Shared SPACE size:
    // The horizontal SPACE keeps its original calculated size.
    // The vertical SPACE will use the same measured dp value.
    private var winXSpacerSizeDp = 0

    private fun updateWinXSpacerSize(view: View) {
        try {
            val sizePx = if (view.width > 0) view.width else view.height
            if (sizePx > 0) {
                winXSpacerSizeDp = (sizePx / resources.displayMetrics.density).toInt()
            }
        } catch (_: Exception) {
        }
    }
    // WINX_SHARED_SPACE_SIZE_PATCH_END

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

    add_match = re.search(r"container\.addView\s*\(\s*frame\s*\)", body)
    if not add_match:
        raise RuntimeError("Original navigation button addView(frame) not found")

    abs_add_end = fn_open + 1 + add_match.end()
    tail = code[abs_add_end:fn_close]
    loop_close_rel = tail.find("}")
    if loop_close_rel < 0:
        raise RuntimeError("Navigation button loop end not found")

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
         
