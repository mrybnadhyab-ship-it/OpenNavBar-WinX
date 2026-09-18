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
