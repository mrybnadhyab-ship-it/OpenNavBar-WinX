import sys
import re

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8") as f:
    code = f.read()

WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"


# ============================================================
# 0. IMPORTS
# ============================================================

imports = [
    "import android.graphics.Typeface",
    "import android.widget.TextView",
    "import android.view.MotionEvent",
    "import java.text.SimpleDateFormat",
    "import java.util.Date",
    "import java.util.Locale",
]

anchor = "import android.accessibilityservice.AccessibilityService"

if anchor not in code:
    raise RuntimeError("AccessibilityService import not found")

for imp in imports:
    if imp not in code:
        code = code.replace(
            anchor,
            anchor + "\n" + imp,
            1
        )


# ============================================================
# 1. WIN X STABLE PATCH
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

    insert = f'''

    // WINX_STABLE_PATCH

    private var isWinXLauncher = false

    private var winXCheckRunnable: Runnable? = null


    private fun getCurrentForegroundPackage(): String {{
        return try {{
            rootInActiveWindow?.packageName?.toString() ?: ""
        }} catch (e: Exception) {{
            ""
        }}
    }}


    private fun checkWinXStateDelayed() {{

        winXCheckRunnable?.let {{
            handler.removeCallbacks(it)
        }}

        winXCheckRunnable = Runnable {{

            val currentPackage =
                getCurrentForegroundPackage()

            if (
                currentPackage ==
                "{WINX_PACKAGE}"
            ) {{

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

                    hideOverlay()
                }}

            }} else {{

                if (isWinXLauncher) {{

                    isWinXLauncher = false

                    forceShowAfterWinX()
                }}
            }}
        }}

        handler.postDelayed(
            winXCheckRunnable!!,
            250
        )
    }}


    private fun forceShowAfterWinX() {{

        val view =
            overlayView ?: return

        view.animate().cancel()

        autoHideRunnable?.let {{
            handler.removeCallbacks(it)
        }}

        autoHideRunnable = null

        view.visibility =
            View.VISIBLE

        view.alpha =
            1f

        view.translationX =
            0f

        view.translationY =
            0f

        isHidden =
            false

        isFullscreenHidden =
            false

        disableRevealZoneTouch()
    }}

    // WINX_STABLE_PATCH_END

'''

    code = (
        code[:match.end()]
        + insert
        + code[match.end():]
    )


# ============================================================
# 2. ACCESSIBILITY EVENT
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

    patch = '''

        // WINX_STABLE_EVENT_PATCH

        checkWinXStateDelayed()

        // WINX_STABLE_EVENT_PATCH_END

'''

    code = (
        code[:match.end()]
        + patch
        + code[match.end():]
    )


# ============================================================
# 3. PROTECT NORMAL SHOW OVERLAY
# ============================================================

def protect_function(name):

    global code

    pattern = re.compile(
        r"(private\s+fun\s+" +
        re.escape(name) +
        r"\s*\([^)]*\)\s*\{)"
    )

    match = pattern.search(code)

    if not match:
        print(
            "Warning: function not found:",
            name
        )
        return

    start = match.end()

    section = code[
        start:start + 700
    ]

    if "if (isWinXLauncher) return" not in section:

        code = (
            code[:start]
            + '''

        if (isWinXLauncher) return

'''
            + code[start:]
        )


protect_function("showOverlay")


# ============================================================
# 4. SHOW ANIMATED
#    Allow explicit reveal from edge swipe while inside Win X
# ============================================================

if "WINX_REVEAL_ARGUMENT_PATCH" not in code:

    pattern = re.compile(
        r"private\s+fun\s+showOverlayAnimated\s*\(\s*\)\s*\{"
        r"\s*"
        r"if\s*\(\s*overlayView\s*==\s*null\s*\|\|\s*!isHidden\s*\)\s*return"
    )

    replacement = '''private fun showOverlayAnimated(
    allowWinXReveal: Boolean = false
) {
    if (overlayView == null || !isHidden) return

    if (isWinXLauncher && !allowWinXReveal) return

    // WINX_REVEAL_ARGUMENT_PATCH
'''

    if not pattern.search(code):
        raise RuntimeError(
            "showOverlayAnimated original block not found"
        )

    code = pattern.sub(
        replacement,
        code,
        count=1
    )


# ============================================================
# 5. CLOCK + DATE
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

    clock_code = '''

    // WINX_CLOCK_DATE_PATCH

    private var winXClockTextView: TextView? = null

    private var winXDateTextView: TextView? = null

    private var winXClockStarted = false


    private val winXClockRunnable =
        object : Runnable {

            override fun run() {

                try {

                    val now =
                        Date()

                    val timeText =
                        SimpleDateFormat(
                            "hh:mm a",
                            Locale.ENGLISH
                        )
                            .format(now)
                            .replace(
                                "AM",
                                "ص"
                            )
                            .replace(
                                "PM",
                                "م"
                            )

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
        buttonColor: Int,
        textRotation: Float = 0f
    ): LinearLayout {

        val layout =
            LinearLayout(this)

        layout.orientation =
            LinearLayout.VERTICAL

        layout.gravity =
            Gravity.CENTER

        layout.setPadding(
            dpToPx(1),
            0,
            dpToPx(1),
            0
        )


        // CLOCK

        val clock =
            TextView(this)

        clock.gravity =
            Gravity.CENTER

        clock.isSingleLine =
            true

        clock.includeFontPadding =
            false

        // Windows-like taskbar size
        clock.textSize =
            9f

        clock.typeface =
            Typeface.DEFAULT

        clock.setTextColor(
            buttonColor
        )

        clock.rotation =
            textRotation


        // DATE

        val date =
            TextView(this)

        date.gravity =
            Gravity.CENTER

        date.isSingleLine =
            true

        date.includeFontPadding =
            false

        // Small Windows-like date
        date.textSize =
            6f

        date.typeface =
            Typeface.DEFAULT

        date.setTextColor(
            buttonColor
        )

        date.rotation =
            textRotation


        layout.addView(
            clock,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )


        layout.addView(
            date,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
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


        return layout
    }

    // WINX_CLOCK_DATE_PATCH_END

'''

    code = (
        code[:match.end()]
        + clock_code
        + code[match.end():]
    )


# ============================================================
# 6. EDGE NAVIGATION LAYOUT + CLOCK
# ============================================================

if "WINX_CLOCK_EDGE_LAYOUT_PATCH" not in code:

    pattern = re.compile(
        r"container\.removeAllViews\(\)\s*"
        r"val order\s*=\s*if\s*\(shouldSwap\).*?"
        r"order\.forEachIndexed\s*\{\s*index,\s*frame\s*->.*?"
        r"container\.addView\(frame\)\s*\}",
        re.S
    )

    match = pattern.search(code)

    if not match:
        raise RuntimeError(
            "Original navigation layout block not found"
        )

    replacement = '''container.removeAllViews()


        /*
         * Clock rotation:
         *
         * Bottom = normal
         * Left   = 90 degrees
         * Right  = -90 degrees
         */
        val clockRotation =
            when (position) {
                "left" -> 90f
                "right" -> -90f
                else -> 0f
            }


        val clockView =
            createWinXClock(
                buttonColor,
                clockRotation
            )


        /*
         * Clock width
         */
        val clockWidth =
            dpToPx(50)


        /*
         * Normal layout:
         *
         * Back | Home | SPACE | Clock | Recent
         */
        val spacer =
            View(this)


        val order: List<View> =
            if (shouldSwap) {

                listOf(
                    recentButton,
                    clockView,
                    spacer,
                    homeButton,
                    backButton
                )

            } else {

                listOf(
                    backButton,
                    homeButton,
                    spacer,
                    clockView,
                    recentButton
                )
            }


        order.forEachIndexed { index, item ->

            val isSpacer =
                item === spacer


            val lp =
                if (isSpacer) {

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

                } else if (item === clockView) {

                    if (isVerticalBar) {

                        LinearLayout.LayoutParams(
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            hitboxSize,
                            0f
                        )

                    } else {

                        LinearLayout.LayoutParams(
                            clockWidth,
                            LinearLayout.LayoutParams.MATCH_PARENT,
                            0f
                        )
                    }

                } else {

                    if (isVerticalBar) {

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
                }


            /*
             * No gap between Clock and Recent Apps.
             */
            if (!isSpacer && index < order.size - 1) {

                if (isVerticalBar) {

                    lp.bottomMargin =
                        if (item === clockView)
                            0
                        else
                            separation

                } else {

                    lp.marginEnd =
                        if (item === clockView)
                            0
                        else
                            separation
                }
            }


            item.layoutParams =
                lp

            container.addView(
                item
            )
        }

        // WINX_CLOCK_EDGE_LAYOUT_PATCH_END
'''

    code = (
        code[:match.start()]
        + replacement
        + code[match.end():]
    )


# ============================================================
# 7. CONTAINER GRAVITY
# ============================================================

if "WINX_EDGE_GRAVITY_PATCH" not in code:

    old = '''
        container.gravity = Gravity.CENTER
'''

    new = '''
        container.gravity =
            if (isVerticalBar)
                Gravity.CENTER_HORIZONTAL
            else
                Gravity.CENTER_VERTICAL

        // WINX_EDGE_GRAVITY_PATCH
'''

    if old in code:

        code = code.replace(
            old,
            new,
            1
        )

    else:

        print(
            "Warning: container gravity line not found"
        )


# ============================================================
# 8. REVEAL ZONE / SWIPE FIX
# ============================================================

if "WINX_REVEAL_ZONE_PATCH" not in code:

    pattern = re.compile(
        r"private\s+fun\s+showRevealZone\s*\(\s*\)\s*\{.*?"
        r"(?=\n\s*private\s+fun\s+removeRevealZone\s*\()",
        re.S
    )

    match = pattern.search(code)

    if not match:
        raise RuntimeError(
            "showRevealZone function not found"
        )

    replacement = '''private fun showRevealZone() {

        // WINX_REVEAL_ZONE_PATCH

        removeRevealZone()


        val position =
            resolvePosition()


        val isVerticalBar =
            position == "left" ||
            position == "right"


        /*
         * Larger invisible touch area.
         *
         * This makes the edge swipe much easier
         * to trigger on Android / HyperOS.
         */
        val thicknessPref =
            prefs.getInt(
                "reveal_zone_thickness",
                20
            )


        val zoneThickness =
            dpToPx(
                maxOf(
                    thicknessPref,
                    12
                )
            )


        val zone =
            FrameLayout(this).apply {

                setBackgroundColor(
                    Color.TRANSPARENT
                )

                isClickable =
                    true

                isFocusable =
                    false


                setOnTouchListener { _, event ->

                    when (event.actionMasked) {

                        MotionEvent.ACTION_DOWN -> {

                            touchStartX =
                                event.rawX

                            touchStartY =
                                event.rawY


                            /*
                             * Important:
                             *
                             * When Win X is currently visible,
                             * touching the edge hides the bar.
                             *
                             * The user can then immediately
                             * swipe from the edge to reveal it.
                             */
                            if (
                                isWinXLauncher &&
                                !isHidden
                            ) {

                                overlayView?.animate()?.cancel()

                                overlayView?.visibility =
                                    View.GONE

                                overlayView?.alpha =
                                    0f

                                overlayView?.translationX =
                                    0f

                                overlayView?.translationY =
                                    0f

                                isHidden =
                                    true

                                enableRevealZoneTouch()
                            }

                            true
                        }


                        MotionEvent.ACTION_UP -> {

                            val requireSlide =
                                prefs.getBoolean(
                                    "require_slide_gesture",
                                    true
                                )


                            val currentPosition =
                                resolvePosition()


                            val deltaX =
                                event.rawX -
                                touchStartX


                            val deltaY =
                                touchStartY -
                                event.rawY


                            /*
                             * Calculate movement according
                             * to the edge position.
                             */
                            val slideDistance =
                                when (currentPosition) {

                                    "left" ->
                                        deltaX

                                    "right" ->
                                        -deltaX

                                    "top" ->
                                        event.rawY - touchStartY

                                    else ->
                                        deltaY
                                }


                            /*
                             * Minimum swipe distance.
                             *
                             * Uses the user setting but never
                             * goes below 15dp.
                             */
                            val requiredDistance =
                                maxOf(
                                    slideThreshold,
                                    dpToPx(15)
                                )


                            val validSwipe =
                                !requireSlide ||
                                slideDistance >= requiredDistance


                            if (validSwipe) {

                                /*
                                 * Explicitly allow the overlay
                                 * to appear while Win X is active.
                                 */
                                showOverlayAnimated(
                                    true
                                )


                                /*
                                 * If keyboard is visible and
                                 * auto-hide is enabled, keep the
                                 * original temporary-hide behavior.
                                 */
                                if (
                                    checkIsKeyboardVisible() &&
                                    prefs.getBoolean(
                                        "auto_hide_enabled",
                                        false
                                    )
                                ) {

                                    autoHideRunnable?.let {
                                        handler.removeCallbacks(it)
                                    }


                                    autoHideRunnable =
                                        Runnable {
                                            hideOverlay()
                                        }


                                    handler.postDelayed(
                                        autoHideRunnable!!,
                                        prefs.getInt(
                                            "auto_hide_delay",
                                            3000
                                        ).toLong()
                                    )
                                }
                            }


                            true
                        }


                        MotionEvent.ACTION_CANCEL -> {

                            true
                        }


                        else -> {

                            true
                        }
                    }
                }
            }


        revealZoneView =
            zone


        val params =
            WindowManager.LayoutParams(

                if (isVerticalBar)
                    zoneThickness
                else
                    WindowManager.LayoutParams.MATCH_PARENT,


                if (!isVerticalBar)
                    zoneThickness
                else
                    WindowManager.LayoutParams.MATCH_PARENT,


                WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,


                WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,


                PixelFormat.TRANSLUCENT
            )


        when (position) {

            "left" -> {
                params.gravity =
                    Gravity.LEFT or
                    Gravity.CENTER_VERTICAL
            }


            "right" -> {
                params.gravity =
                    Gravity.RIGHT or
                    Gravity.CENTER_VERTICAL
            }


            "top" -> {
                params.gravity =
                    Gravity.TOP or
                    Gravity.CENTER_HORIZONTAL
            }


            else -> {
                params.gravity =
                    Gravity.BOTTOM or
                    Gravity.CENTER_HORIZONTAL
            }
        }


        /*
         * When overlay is visible,
         * the invisible reveal zone must NOT intercept touches.
         */
        if (!isHidden) {

            params.flags =
                params.flags or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE
        }


        windowManager.addView(
            revealZoneView,
            params
        )

        // WINX_REVEAL_ZONE_PATCH_END
    }

'''

    code = (
        code[:match.start()]
        + replacement
        + code[match.end():]
    )


# ============================================================
# 9. CLOCK CLEANUP
# ============================================================

if "WINX_CLOCK_CLEANUP_PATCH" not in code:

    pattern = re.compile(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)"
    )

    match = pattern.search(code)

    if match:

        cleanup = '''

        // WINX_CLOCK_CLEANUP_PATCH

        handler.removeCallbacks(
            winXClockRunnable
        )

        winXClockStarted = false

'''

        code = (
            code[:match.end()]
            + cleanup
            + code[match.end():]
        )


# ============================================================
# 10. SAVE
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)


print("================================================")
print(" OpenNavBar Win X PATCH")
print("================================================")
print("Win X package:", WINX_PACKAGE)
print("")
print("Win X detection:")
print("  rootInActiveWindow")
print("  delay: 250ms")
print("")
print("Win X behavior:")
print("  Inside Win X  -> HIDE")
print("  Outside Win X -> FORCE SHOW")
print("")
print("Clock:")
print("  Windows-like taskbar size")
print("  Time: 9sp")
print("  Date: 6sp")
print("  Clock width: 50dp")
print("")
print("Navigation layout:")
print("  Back | Home | SPACE | Clock | Recent")
print("")
print("Swipe:")
print("  Reveal zone: minimum 12dp")
print("  Default: 20dp")
print("  Minimum swipe: 15dp")
print("  Win X reveal explicitly allowed")
print("")
print("================================================")
print("PATCH COMPLETE")
print("================================================")
