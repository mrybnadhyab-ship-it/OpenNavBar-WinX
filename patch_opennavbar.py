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
# 2. WIN X STATE
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

        val view =
            overlayView ?: return

        view.animate().cancel()

        autoHideRunnable?.let {
            handler.removeCallbacks(it)
        }

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
# 4. PROTECT showOverlay()
# ============================================================

if "WINX_SHOW_OVERLAY_PROTECTION" not in code:

    pattern = re.compile(
        r"(private\s+fun\s+showOverlay\s*\([^)]*\)\s*\{)"
    )

    match = pattern.search(code)

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
# 5. PROTECT showOverlayAnimated()
#
# Normal calls cannot reveal the bar inside Win X.
# Reveal Zone can explicitly bypass this protection.
# ============================================================

if "WINX_SHOW_ANIMATED_PROTECTION" not in code:

    pattern = re.compile(
        r"private\s+fun\s+showOverlayAnimated\s*\(\s*\)\s*\{"
    )

    match = pattern.search(code)

    if not match:
        raise RuntimeError(
            "showOverlayAnimated() not found"
        )

    new_signature = r'''private fun showOverlayAnimated(
        allowWinXReveal: Boolean = false
    ) {'''

    code = (
        code[:match.start()]
        + new_signature
        + code[match.end():]
    )

    pattern = re.compile(
        r"(private\s+fun\s+showOverlayAnimated\s*\("
        r"\s*allowWinXReveal\s*:\s*Boolean\s*=\s*false\s*\)"
        r"\s*\{)"
    )

    match = pattern.search(code)

    if not match:
        raise RuntimeError(
            "Modified showOverlayAnimated() not found"
        )

    guard = r'''
        
        // WINX_SHOW_ANIMATED_PROTECTION

        if (isWinXLauncher && !allowWinXReveal) {
            return
        }

'''

    code = (
        code[:match.end()]
        + guard
        + code[match.end():]
    )


# ============================================================
# 6. REVEAL ZONE
#
# Preserve the original swipe.
# Only the actual reveal gesture is allowed to bypass Win X.
# ============================================================

if "WINX_REVEAL_ZONE_PATCH" not in code:

    old = '''if (!requireSlide || slideDistance >= slideThreshold) {
                        showOverlayAnimated()
'''

    new = '''if (!requireSlide || slideDistance >= slideThreshold) {

                        showOverlayAnimated(true)

                        // WINX_REVEAL_ZONE_PATCH

                        if (isWinXLauncher) {

                            autoHideRunnable?.let {
                                handler.removeCallbacks(it)
                            }

                            autoHideRunnable = Runnable {
                                hideOverlay()
                            }

                            handler.postDelayed(
                                autoHideRunnable!!,
                                10000L
                            )
                        }
'''

    if old not in code:
        raise RuntimeError(
            "Reveal Zone showOverlayAnimated() call not found"
        )

    code = code.replace(
        old,
        new,
        1
    )


# ============================================================
# 7. CLOCK + DATE
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
        textColor: Int,
        rotation: Float
    ): LinearLayout {

        val clockLayout =
            LinearLayout(this)

        clockLayout.orientation =
            LinearLayout.VERTICAL

        clockLayout.gravity =
            Gravity.CENTER

        clockLayout.setPadding(
            0,
            0,
            0,
            0
        )


        val clock =
            TextView(this)

        clock.gravity =
            Gravity.CENTER

        clock.isSingleLine =
            true

        clock.includeFontPadding =
            false

        clock.textSize =
            9f

        clock.typeface =
            Typeface.DEFAULT

        clock.setTextColor(
            textColor
        )

        clock.rotation =
            rotation


        val date =
            TextView(this)

        date.gravity =
            Gravity.CENTER

        date.isSingleLine =
            true

        date.includeFontPadding =
            false

        date.textSize =
            6f

        date.typeface =
            Typeface.DEFAULT

        date.setTextColor(
            textColor
        )

        date.rotation =
            rotation


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
# 8. CLOCK LAYOUT
# ============================================================

if "WINX_CLOCK_LAYOUT_PATCH" not in code:

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
            "Navigation button layout block not found"
        )

    replacement = r'''container.removeAllViews()

        // WINX_CLOCK_LAYOUT_PATCH

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

        val clockWidth =
            dpToPx(50)

        /*
         * Bottom:
         *
         * Back | Home | SPACE | Clock | Recent
         *
         * Swapped:
         *
         * Recent | Clock | SPACE | Home | Back
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
             * Clock and Recent Apps stay directly adjacent.
             */

            if (
                !isSpacer &&
                index < order.size - 1
            ) {

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


        // WINX_CLOCK_LAYOUT_PATCH_END
'''

    code = (
        code[:match.start()]
        + replacement
        + code[match.end():]
    )


# ============================================================
# 9. CONTAINER GRAVITY
# ============================================================

if "WINX_CLOCK_GRAVITY_PATCH" not in code:

    old = "container.gravity = Gravity.CENTER"

    new = '''container.gravity =
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
            "Warning: container.gravity line not found"
        )


# ============================================================
# 10. CLOCK CLEANUP
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

        winXClockStarted =
            false

        winXClockTextView =
            null

        winXDateTextView =
            null

'''

        code = (
            code[:match.end()]
            + cleanup
            + code[match.end():]
        )


# ============================================================
# 11. SAVE
# ============================================================

with open(path, "w", encoding="utf-8") as f:
    f.write(code)


print("================================================")
print(" OPENNAVBAR WIN X + CLOCK PATCH")
print("================================================")
print("")
print("Patch applied successfully.")
print("")
print("Win X package:")
print(WINX_PACKAGE)
print("")
print("Win X:")
print("  Inside Win X  -> HIDE")
print("  Outside Win X -> FORCE SHOW")
print("  Detection     -> rootInActiveWindow")
print("  Delay         -> 250ms")
print("")
print("Reveal Zone:")
print("  Swipe preserved")
print("  Win X reveal  -> allowed")
print("  Auto hide     -> 10 seconds")
print("")
print("Clock:")
print("  Time          -> 9sp")
print("  Date          -> 6sp")
print("  Width         -> 50dp")
print("  Font          -> Normal")
print("")
print("Layout:")
print("  Back | Home | SPACE | Clock | Recent")
print("  Swapped: Recent | Clock | SPACE | Home | Back")
print("")
print("Protection:")
print("  showOverlay() protected")
print("  showOverlayAnimated() protected")
print("  Reveal Zone bypass preserved")
print("")
print("================================================")
print("PATCH COMPLETE")
print("================================================")
