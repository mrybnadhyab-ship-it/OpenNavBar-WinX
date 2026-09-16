================
# 4. PROTECT SHOW FUNCTIONS
# ============================================================

def protect_function(name):

    global code

    pattern = re.compile(
        r"(fun\s+" +
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
        start:start + 600
    ]

    if "if (isWinXLauncher) return" not in section:

        code = (
            code[:start]
            + """

        if (isWinXLauncher) return

"""
            + code[start:]
        )


protect_function("showOverlay")
protect_function("showOverlayAnimated")


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

    clock_code = """

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


                    /*
                     * 12-hour clock.
                     *
                     * AM -> ص
                     * PM -> م
                     */
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


                    /*
                     * Date:
                     *
                     * yyyy/MM/dd
                     */
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
        buttonColor: Int
    ): LinearLayout {

        val layout =
            LinearLayout(this)


        layout.orientation =
            LinearLayout.VERTICAL


        layout.gravity =
            Gravity.CENTER


        /*
         * Minimal horizontal padding.
         */
        layout.setPadding(
            dpToPx(1),
            0,
            dpToPx(1),
            0
        )


        /*
         * CLOCK
         */
        val clock =
            TextView(this)


        clock.gravity =
            Gravity.CENTER


        clock.isSingleLine =
            true


        /*
         * Clock is larger.
         */
        clock.textSize =
            13f


        clock.typeface =
            Typeface.DEFAULT_BOLD


        clock.setTextColor(
            buttonColor
        )


        /*
         * DATE
         */
        val date =
            TextView(this)


        date.gravity =
            Gravity.CENTER


        date.isSingleLine =
            true


        /*
         * Date is smaller.
         */
        date.textSize =
            8f


        date.typeface =
            Typeface.DEFAULT


        date.setTextColor(
            buttonColor
        )


        /*
         * Clock.
         */
        layout.addView(
            clock,
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        )


        /*
         * Date directly underneath.
         */
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


        /*
         * Start clock only once.
         */
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

"""

    code = (
        code[:match.end()]
        + clock_code
        + code[match.end():]
    )


# ============================================================
# 6. CLOCK ORDER + POSITION
# ============================================================

if "WINX_CLOCK_ORDER_PATCH" not in code:

    pattern = re.compile(
        r"val order = if \(shouldSwap\)\s*"
        r"listOf\(recentButton,\s*homeButton,\s*backButton\)\s*"
        r"else\s*"
        r"listOf\(backButton,\s*homeButton,\s*recentButton\)"
    )

    match = pattern.search(code)

    if not match:
        raise RuntimeError(
            "Original navigation order not found"
        )


    replacement = """

        // WINX_CLOCK_ORDER_PATCH


        /*
         * Create clock + date.
         */
        val clockView =
            createWinXClock(
                buttonColor
            )


        /*
         * Smaller width makes the clock
         * closer to Recent Apps.
         */
        val clockWidth =
            dpToPx(50)


        clockView.layoutParams =
            LinearLayout.LayoutParams(
                clockWidth,
                LinearLayout.LayoutParams.MATCH_PARENT
            )


        /*
         * Normal portrait order:
         *
         * Back
         * Home
         * Clock + Date
         * Recent Apps
         */
        val order =
            if (shouldSwap)

                listOf(
                    recentButton,
                    clockView,
                    homeButton,
                    backButton
                )

            else

                listOf(
                    backButton,
                    homeButton,
                    clockView,
                    recentButton
                )


        // WINX_CLOCK_ORDER_PATCH_END

"""


    code = (
        code[:match.start()]
        + replacement
        + code[match.end():]
    )


# ============================================================
# 7. REMOVE GAP AFTER CLOCK
# ============================================================

if "WINX_CLOCK_GAP_PATCH" not in code:

    pattern = re.compile(
        r"if\s*\(index\s*<\s*order\.size\s*-\s*1\)\s*\{"
        r"\s*"
        r"if\s*\(isVerticalBar\)\s*"
        r"lp\.bottomMargin\s*=\s*separation\s*"
        r"else\s*"
        r"lp\.marginEnd\s*=\s*separation\s*"
        r"\}"
    )


    replacement = """

            // WINX_CLOCK_GAP_PATCH

            if (index < order.size - 1) {

                if (isVerticalBar) {

                    lp.bottomMargin =
                        if (frame === clockView)
                            0
                        else
                            separation

                } else {

                    lp.marginEnd =
                        if (frame === clockView)
                            0
                        else
                            separation
                }
            }

            // WINX_CLOCK_GAP_PATCH_END

"""


    if pattern.search(code):

        code = pattern.sub(
            replacement,
            code,
            count=1
        )

    else:

        print(
            "Warning: original separation block not found"
        )


# ============================================================
# 8. CLEAN CLOCK ON DESTROY
# ============================================================

if "WINX_CLOCK_DESTROY_PATCH" not in code:

    marker = "override fun onDestroy() {"

    if marker in code:

        code = code.replace(
            marker,
            """override fun onDestroy() {

        // WINX_CLOCK_DESTROY_PATCH

        handler.removeCallbacks(
            winXClockRunnable
        )

        winXClockTextView = null

        winXDateTextView = null

        winXClockStarted = false

        // WINX_CLOCK_DESTROY_PATCH_END
""",
            1
        )


# ============================================================
# 9. SAVE
# ============================================================

with open(
    path,
    "w",
    encoding="utf-8"
) as f:

    f.write(code)


print("==============================================")
print("WIN X STABLE + CLOCK + DATE")
print("==============================================")
print("")
print("ORDER:")
print("Back")
print("Home")
print("Clock + Date")
print("Recent Apps")
print("")
print("Clock:")
print("13sp / Bold")
print("12-hour")
print("ص / م")
print("")
print("Date:")
print("8sp / Normal")
print("yyyy/MM/dd")
print("")
print("Clock width:")
print("50dp")
print("")
print("Clock -> Recent gap:")
print("0dp")
print("")
print("Win X:")
print("HIDE")
print("")
print("Outside Win X:")
print("FORCE SHOW")
print("")
print("Reveal swipe:")
print("Existing reveal zone preserved")
print("")
print("No app modifications")
print("No button logic modification")
print("==============================================")
import sys
import re

if len(sys.argv) != 2:
    print("Usage: python3 patch_opennavbar.py <NavigationOverlayService.kt>")
    sys.exit(1)

path = sys.argv[1]

with open(path, "r", encoding="utf-8-sig") as f:
    code = f.read()


# ============================================================
# 0. CLEAN BROKEN IMPORTS
# ============================================================

broken_imports = [
    "java.util.Locale",
    "java.text.SimpleDateFormat",
    "java.util.Date",
    "android.graphics.Typeface",
    "android.widget.TextView",
]

for broken in broken_imports:
    code = re.sub(
        r"(?m)^[ \t]*" + re.escape(broken) + r"[ \t]*\r?\n",
        "",
        code
    )


# ============================================================
# 1. IMPORTS
# ============================================================

imports = [
    "import android.graphics.Typeface",
    "import android.widget.TextView",
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

    insert = r"""

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

"""

    code = (
        code[:match.end()]
        + insert
        + code[match.end():]
    )


# ============================================================
# 3. WIN X ACCESSIBILITY EVENT
# ============================================================

if "WINX_STABLE_EVENT_PATCH" not in code:

    match = re.search(
        r"(override\s+fun\s+onAccessibilityEvent\s*"
        r"\(\s*event\s*:\s*AccessibilityEvent\?\s*\)\s*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "onAccessibilityEvent not found"
        )

    patch = r"""

        // WINX_STABLE_EVENT_PATCH

        checkWinXStateDelayed()

        // WINX_STABLE_EVENT_PATCH_END

"""

    code = (
        code[:match.end()]
        + patch
        + code[match.end():]
    )


# ============================================================
# 4. PROTECT ONLY NORMAL SHOW
# ============================================================

def protect_function(name):

    global code

    pattern = re.compile(
        r"(fun\s+" +
        re.escape(name) +
        r"\s*\([^)]*\)\s*\{)"
    )

    match = pattern.search(code)

    if not match:
        print("Warning: function not found:", name)
        return

    start = match.end()

    section = code[
        start:start + 600
    ]

    if "if (isWinXLauncher) return" not in section:

        code = (
            code[:start]
            + """

        if (isWinXLauncher) return

"""
            + code[start:]
        )


# IMPORTANT:
# showOverlay() is protected.
# showOverlayAnimated() is NOT protected here because
# the reveal gesture must be allowed to show the bar in Win X.

protect_function("showOverlay")


# ============================================================
# 5. MAKE showOverlayAnimated ALLOW EXPLICIT WIN X REVEAL
# ============================================================

if "WINX_REVEAL_ARGUMENT_PATCH" not in code:

    pattern = re.compile(
        r"private\s+fun\s+showOverlayAnimated\s*\(\s*\)\s*\{"
        r"\s*"
        r"if\s*\(\s*overlayView\s*==\s*null\s*\|\|\s*!isHidden\s*\)\s*return"
    )

    replacement = r"""private fun showOverlayAnimated(
        allowWinXReveal: Boolean = false
    ) {
        if (overlayView == null || !isHidden) return

        if (isWinXLauncher && !allowWinXReveal) return

        // WINX_REVEAL_ARGUMENT_PATCH
"""

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

    clock_code = r"""

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


        /*
         * CLOCK
         *
         * Keep the existing design:
         * 13sp / Bold
         */
        val clock =
            TextView(this)

        clock.gravity =
            Gravity.CENTER

        clock.isSingleLine =
            true

        clock.textSize =
            13f

        clock.typeface =
            Typeface.DEFAULT_BOLD

        clock.setTextColor(
            buttonColor
        )

        clock.rotation =
            textRotation


        /*
         * DATE
         *
         * Keep the existing design:
         * 8sp / Normal
         */
        val date =
            TextView(this)

        date.gravity =
            Gravity.CENTER

        date.isSingleLine =
            true

        date.textSize =
            8f

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

"""

    code = (
        code[:match.end()]
        + clock_code
        + code[match.end():]
    )


# ============================================================
# 7. EDGE LAYOUT + CLOCK POSITION
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

    replacement = r"""container.removeAllViews()

    /*
     * Clock rotation:
     *
     * Bottom = normal
     * Left   = clockwise
     * Right  = counter-clockwise
     */
    val clockRotation =
        when (position) {
            "left" -> 90f
            "right" -> -90f
            else -> 0f
        }


    /*
     * Existing clock design is preserved.
     */
    val clockView =
        createWinXClock(
            buttonColor,
            clockRotation
        )


    /*
     * Keep clock width exactly 50dp.
     */
    val clockWidth =
        dpToPx(50)


    /*
     * One flexible spacer.
     *
     * Normal:
     *
     * Back | Home | spacer | Clock | Recent
     *
     * This gives:
     * Back at edge
     * Recent Apps at opposite edge
     * Clock directly beside Recent Apps
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

                /*
                 * Flexible empty space.
                 */
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

                /*
                 * Clock keeps its 50dp width.
                 */
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

                /*
                 * Normal navigation buttons.
                 */
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
         * Keep the clock directly beside Recent Apps.
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
"""

    code = (
        code[:match.start()]
        + replacement
        + code[match.end():]
    )


# ============================================================
# 8. CONTAINER GRAVITY
# ============================================================

if "WINX_EDGE_GRAVITY_PATCH" not in code:

    old = """
    container.gravity = Gravity.CENTER
"""

    new = """
    container.gravity =
        if (isVerticalBar)
            Gravity.CENTER_HORIZONTAL
        else
            Gravity.CENTER_VERTICAL

    // WINX_EDGE_GRAVITY_PATCH
"""

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
# 9. REVEAL ZONE / SWIPE FIX
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

    replacement = r"""private fun showRevealZone() {

    // WINX_REVEAL_ZONE_PATCH

    removeRevealZone()


    val position =
        resolvePosition()


    val isVerticalBar =
        position == "left" ||
        position == "right"


    /*
     * Keep the user's preference,
     * but never make the swipe area too thin.
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


            setOnTouchListener { _, event ->

                when (event.action) {

                    MotionEvent.ACTION_DOWN -> {

                        /*
                         * If Win X is active and the hide
                         * animation has not completed yet,
                         * force the overlay into the hidden state.
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
                        }


                        touchStartX =
                            event.rawX

                        touchStartY =
                            event.rawY


                        true
                    }


                    MotionEvent.ACTION_UP -> {

                        val requireSlide =
                            prefs.getBoolean(
                                "require_slide_gesture",
                                true
                            )


                        val deltaX =
                            event.rawX -
                            touchStartX


                        val deltaY =
                            touchStartY -
                            event.rawY


                        val slideDistance =
                            when (position) {

                                "left" ->
                                    deltaX

                                "right" ->
                                    -deltaX

                                else ->
                                    deltaY
                            }


                        /*
                         * Keep the user's threshold,
                         * but require at least a small
                         * meaningful movement.
                         */
                        val requiredDistance =
                            maxOf(
                                slideThreshold,
                                dpToPx(15)
                            )


                        if (
                            !requireSlide ||
                            slideDistance >= requiredDistance
                        ) {

                            /*
                             * TRUE is important:
                             *
                             * It explicitly allows the
                             * reveal gesture to show the
                             * navigation bar while Win X
                             * is 
