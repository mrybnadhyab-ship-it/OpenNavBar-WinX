======
# 5. CLOCK + DATE
# ============================================================

if "WINX_CLOCK_DATE_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code,
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

        val isVerticalClock =
            rotation == 90f || rotation == -90f


        val clockLayout = LinearLayout(this).apply {

            orientation = LinearLayout.VERTICAL

            gravity = Gravity.CENTER

            setPadding(
                if (isVerticalClock) dpToPx(2) else 0,
                0,
                if (isVerticalClock) dpToPx(2) else 0,
                0
            )

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

            // التاريخ أصبح بنفس حجم الساعة
            textSize = 9f

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
# 5.5. PROTECT showOverlayAnimated()
# ============================================================

if "WINX_SHOW_ANIMATED_PROTECTION" not in code:

    fn = find_function(
        code,
        "showOverlayAnimated"
    )

    if not fn:
        raise RuntimeError(
            "showOverlayAnimated() not found"
        )

    _, fn_open, _ = fn

    guard = """
        // WINX_SHOW_ANIMATED_PROTECTION
        if (isWinXLauncher) return
"""

    code = (
        code[:fn_open + 1]
        + guard
        + code[fn_open + 1:]
    )


# ============================================================
# 6. INSERT CLOCK WITHOUT REPLACING ORIGINAL BUTTON LAYOUT
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

    loop_match = re.search(
        r"order\.forEachIndexed\s*\{",
        body
    )

    if not loop_match:
        raise RuntimeError(
            "Original navigation button order loop not found"
        )

    loop_open_rel = body.find(
        "{",
        loop_match.start(),
        loop_match.end()
    )

    if loop_open_rel < 0:
        raise RuntimeError(
            "Navigation button loop opening brace not found"
        )

    loop_close_rel = find_matching_brace(
        body,
        loop_open_rel
    )

    if loop_close_rel < 0:
        raise RuntimeError(
            "Navigation button loop closing brace not found"
        )

    insert_pos = (
        fn_open
        + 1
        + loop_close_rel
        + 1
    )


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

            // الوضع الرأسي:
            // الساعة والتاريخ في منتصف الشريط
            // مع مساحة كاملة للعرض الأفقي
            LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                hitboxSize,
                0f
            )

        } else {

            // الوضع الأفقي يبقى كما هو
            LinearLayout.LayoutParams(
                dpToPx(50),
                LinearLayout.LayoutParams.MATCH_PARENT,
                0f
            )
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

        // WINX_CLOCK_LAYOUT_PATCH_END
'''

    code = (
        code[:insert_pos]
        + clock_layout_patch
        + code[insert_pos:]
    )


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
# 8. CLOCK CLEANUP
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
print("Clock: 9sp time / 9sp date / 50dp / non-touch")
print("Portrait: centered clock + date")
print("Gmail: NOT INCLUDED")
print("Swipe: ORIGINAL SWIPE/REVEAL CODE PRESERVED")
print("================================================")
print("PATCH COMPLETE")
print("================================================")
patch_opennavbar.py
