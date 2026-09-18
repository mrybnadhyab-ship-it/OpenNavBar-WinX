patch_opennavbar.pyckable = false
        }

        val clock =
            TextView(this).apply {

            gravity =
                Gravity.CENTER

            isSingleLine = true

            includeFontPadding =
                false

            textSize = 9f

            typeface =
                Typeface.DEFAULT

            setTextColor(
                textColor
            )

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

            includeFontPadding =
                false

            textSize = 9f

            typeface =
                Typeface.DEFAULT

            setTextColor(
                textColor
            )

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

            topMargin =
                dpToPx(1)
        }

        clockLayout.addView(
            date,
            dateParams
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
# 7. INSERT CLOCK
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

    abs_add_end =
        fn_open + 1 + add_match.end()

    tail =
        code[abs_add_end:fn_close]

    loop_close_rel =
        tail.find("}")

    if loop_close_rel < 0:
        raise RuntimeError(
            "Navigation button loop end not found"
        )

    insert_pos =
        abs_add_end + loop_close_rel + 1

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

    old = (
        "container.gravity = Gravity.CENTER"
    )

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
# 10. LONG PRESS BACK -> WIN X
# ============================================================

if "WINX_LONG_BACK_START_PATCH" not in code:

    match = re.search(
        r"(class\s+NavigationOverlayService[^{]*\{)",
        code
    )

    if not match:
        raise RuntimeError(
            "NavigationOverlayService class not found"
        )

    long_back_patch = r'''

    // WINX_LONG_BACK_START_PATCH

    private var winXBackLongPressed = false
    private var winXBackDown = false

    private val winXBackLongPressRunnable =
        Runnable {

        if (winXBackDown) {

            winXBackLongPressed =
                true

            try {

                val launchIntent =
                    packageManager
                        .getLaunchIntentForPackage(
                            "com.InternityLabs.Launcher.WinX"
                        )

                if (launchIntent != null) {

                    launchIntent.addFlags(
                        Intent.FLAG_ACTIVITY_NEW_TASK or
                        Intent.FLAG_ACTIVITY_CLEAR_TOP
                    )

                    startActivity(
                        launchIntent
                    )
                }

            } catch (_: Exception) {
            }
        }
    }

    private fun handleWinXBackKey(
        event: KeyEvent
    ): Boolean {

        if (
            event.keyCode !=
            KeyEvent.KEYCODE_BACK
        ) {
            return false
        }

        when (event.action) {

            KeyEvent.ACTION_DOWN -> {

                if (!winXBackDown) {

                    winXBackDown = true

                    winXBackLongPressed =
                        false

                    handler.removeCallbacks(
                        winXBackLongPressRunnable
                    )

                    handler.postDelayed(
                        winXBackLongPressRunnable,
                        550L
                    )
                }

                return true
            }

            KeyEvent.ACTION_UP -> {

                handler.removeCallbacks(
                    winXBackLongPressRunnable
                )

                val wasLongPressed =
                    winXBackLongPressed

                winXBackDown = false

                winXBackLongPressed =
                    false

                if (!wasLongPressed) {

                    performGlobalAction(
                        AccessibilityService
                            .GLOBAL_ACTION_BACK
                    )
                }

                return true
            }
        }

        return true
    }

    // WINX_LONG_BACK_START_PATCH_END
'''

    code = (
        code[:match.end()]
        + long_back_patch
        + code[match.end():]
    )


# ============================================================
# 11. ON KEY EVENT
# ============================================================

if "WINX_LONG_BACK_ON_KEY_EVENT" not in code:

    key_match = re.search(
        r"(override\s+fun\s+onKeyEvent\s*\(\s*"
        r"event\s*:\s*KeyEvent\s*\)\s*:\s*Boolean\s*\{)",
        code
    )

    if key_match:

        key_event_patch = r'''
        // WINX_LONG_BACK_ON_KEY_EVENT

        if (
            event.keyCode ==
            KeyEvent.KEYCODE_BACK
        ) {

            return handleWinXBackKey(
                event
            )
        }

'''

        code = (
            code[:key_match.end()]
            + key_event_patch
            + code[key_match.end():]
        )

    else:

        insert_at =
            code.rfind("\n}")

        if insert_at < 0:
            raise RuntimeError(
                "Could not find final class brace"
            )

        key_event_method = r'''

    // WINX_LONG_BACK_ON_KEY_EVENT

    override fun onKeyEvent(
        event: KeyEvent
    ): Boolean {

        if (
            event.keyCode ==
            KeyEvent.KEYCODE_BACK
        ) {

            return handleWinXBackKey(
                event
            )
        }

        return super.onKeyEvent(
            event
        )
    }

    // WINX_LONG_BACK_ON_KEY_EVENT_END
'''

        code = (
            code[:insert_at]
            + key_event_method
            + code[insert_at:]
        )


# ============================================================
# 12. LONG PRESS CLEANUP
# ============================================================

if "WINX_LONG_BACK_CLEANUP_PATCH" not in code:

    destroy_match = re.search(
        r"(override\s+fun\s+onDestroy\s*\(\s*\)\s*\{)",
        code
    )

    if destroy_match:

        cleanup = r'''
        // WINX_LONG_BACK_CLEANUP_PATCH

        handler.removeCallbacks(
            winXBackLongPressRunnable
        )

        winXBackDown = false

        winXBackLongPressed = false

'''

        code = (
            code[:destroy_match.end()]
            + cleanup
            + code[destroy_match.end():]
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
print(" OPENNAVBAR WIN X 9F FIX")
print("================================================")
print("")
print("Win X package:")
print(WINX_PACKAGE)
print("")
print("Win X: hide only on Win X launcher")
print("Portrait fullscreen: FIXED / ALWAYS VISIBLE")
print("Landscape fullscreen: ORIGINAL BEHAVIOR")
print("")
print("Clock: 9sp time")
print("Date: 9sp")
print("Clock gap: 1dp")
print("Clock: non-touch")
print("")
print("Long Back: 550ms -> Win X Launcher")
print("Normal Back: GLOBAL_ACTION_BACK")
print("")
print("Original Swipe/Reveal: PRESERVED")
print("================================================")
print("PATCH COMPLETE")
print("================================================")
