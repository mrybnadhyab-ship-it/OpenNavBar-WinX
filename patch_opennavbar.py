#!/usr/bin/env python3
import re
import sys
from pathlib import Path

p = Path(sys.argv[1])
s = p.read_text(encoding="utf-8")

# Keep the existing successful WinX patch. Only debounce WinX state changes
# so a transient AccessibilityEvent cannot make the navbar flicker/disappear.

if 'private var isWinXLauncher = false' not in s:
    m = re.search(r'(class\s+NavigationOverlayService[^\{]*\{)', s)
    if not m:
        raise SystemExit("Could not locate NavigationOverlayService class.")
    insert = m.group(1) + '''
    private var isWinXLauncher = false
    private var winXStateRunnable: Runnable? = null
    private companion object {
        const val WINX_PACKAGE = "com.InternityLabs.Launcher.WinX"
    }
'''
    s = s[:m.start()] + insert + s[m.end():]

old = '''            val foregroundPackage = event.packageName?.toString()
            val nowWinX = foregroundPackage == WINX_PACKAGE
            if (nowWinX != isWinXLauncher) {
                isWinXLauncher = nowWinX
                if (nowWinX) {
                    hideOverlay()
                } else {
                    showOverlayAnimated()
                }
            }
'''

new = '''            val foregroundPackage = event.packageName?.toString()
            if (!foregroundPackage.isNullOrEmpty()) {
                val targetState = foregroundPackage == WINX_PACKAGE

                // Accessibility can briefly report another package while WinX
                // is still visible. Wait 500 ms before changing navbar state.
                winXStateRunnable?.let { handler.removeCallbacks(it) }
                val pendingState = targetState
                winXStateRunnable = Runnable {
                    if (pendingState != isWinXLauncher) {
                        isWinXLauncher = pendingState
                        if (pendingState) {
                            hideOverlay()
                        } else {
                            showOverlayAnimated()
                        }
                    }
                }
                handler.postDelayed(winXStateRunnable!!, 500L)
            }
'''

if old in s:
    s = s.replace(old, new, 1)
elif 'val targetState = foregroundPackage == WINX_PACKAGE' not in s:
    raise SystemExit("Could not locate the existing WinX detection block.")

# The successful patch must be allowed to restore the navbar after leaving WinX.
# Remove only an accidental global guard before showOverlayAnimated().
s = re.sub(r'\n\s*if \(isWinXLauncher\) return\n', '\n', s, count=1)

# Clean up the pending callback when the service is destroyed.
if 'winXStateRunnable?.let { handler.removeCallbacks(it) }' not in s:
    marker = 'override fun onDestroy()'
    pos = s.find(marker)
    if pos != -1:
        brace = s.find('{', pos)
        if brace != -1:
            s = s[:brace + 1] + '\n        winXStateRunnable?.let { handler.removeCallbacks(it) }\n' + s[brace + 1:]

p.write_text(s, encoding="utf-8")
print("Patched WinX anti-flicker:", p)


# Add only Gmail to the existing Win-X bar.
# 16dp icon, immediately after Home, on the clock/time side.
if 'WINX_GMAIL_BUTTON_PATCH' not in s:
    if 'fun configureOverlayView' not in s:
        raise SystemExit("Could not locate configureOverlayView().")

    func_pos = s.find('fun configureOverlayView')
    loop_pos = s.find('order.forEachIndexed', func_pos)
    if loop_pos == -1:
        raise SystemExit("Could not locate the existing order.forEachIndexed loop.")

    brace_pos = s.find('{', loop_pos)
    if brace_pos == -1:
        raise SystemExit("Could not locate the start of order.forEachIndexed block.")

    depth = 0
    i = brace_pos
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escaped = False
    while i < len(s):
        c = s[i]
        n = s[i + 1] if i + 1 < len(s) else ''
        if in_line_comment:
            if c == '\n':
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if c == '*' and n == '/':
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if in_string:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            if escaped:
                escaped = False
            elif c == '\\':
                escaped = True
            elif c == "'":
                in_char = False
            i += 1
            continue
        if c == '/' and n == '/':
            in_line_comment = True
            i += 2
            continue
        if c == '/' and n == '*':
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
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end_pos = i + 1
                break
        i += 1
    else:
        raise SystemExit("Could not find the end of order.forEachIndexed block.")

    gmail_code = r'''

        // WINX_GMAIL_BUTTON_PATCH
        val winXGmailButton = android.widget.FrameLayout(this).apply {
            isClickable = true
            isFocusable = true
            isLongClickable = false

            val gmailIcon = android.widget.ImageView(this@NavigationOverlayService).apply {
                try {
                    val gmailInfo = packageManager.getApplicationInfo("com.google.android.gm", 0)
                    setImageDrawable(packageManager.getApplicationIcon(gmailInfo))
                } catch (_: Exception) {
                }
                scaleType = android.widget.ImageView.ScaleType.CENTER_INSIDE
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
                    val intent = packageManager.getLaunchIntentForPackage("com.google.android.gm")
                    if (intent != null) {
                        intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
                        startActivity(intent)
                    }
                } catch (_: Exception) {
                }
            }
        }

        val winXGmailParams = if (isVerticalBar) {
            android.widget.LinearLayout.LayoutParams(
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                hitboxSize,
                0f
            )
        } else {
            android.widget.LinearLayout.LayoutParams(
                hitboxSize,
                android.widget.LinearLayout.LayoutParams.MATCH_PARENT,
                0f
            )
        }

        // Home is the first existing button. Put Gmail directly after it,
        // toward the existing clock/date area.
        val winXGmailIndex = if (container.childCount >= 1) 1 else 0
        container.addView(winXGmailButton, winXGmailIndex, winXGmailParams)
        // WINX_GMAIL_BUTTON_PATCH_END
'''
    s = s[:end_pos] + gmail_code + s[end_pos:]

p.write_text(s, encoding='utf-8')
print("Patched WinX anti-flicker + Gmail 16dp beside Home:", p)
