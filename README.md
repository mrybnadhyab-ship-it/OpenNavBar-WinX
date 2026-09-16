# OpenNavBar — Win X edition

هذه الحزمة مجهزة للبناء عبر GitHub Actions.

التعديل المقصود:
- داخل Win X Launcher يتم إخفاء OpenNavBar.
- عند مغادرة Win X إلى Facebook أو MiXplorer أو أي تطبيق آخر يظهر OpenNavBar.
- لا يتم تغيير إعدادات Gesture Navigation نفسها.

## البناء
1. أنشئ مستودعًا جديدًا على GitHub.
2. ارفع محتويات هذه الحزمة.
3. افتح Actions.
4. اختر Build OpenNavBar WinX edition.
5. اضغط Run workflow.
6. بعد نجاح البناء حمّل Artifact باسم OpenNavBar-WinX-debug.
7. فك الضغط وثبّت APK.

الـ debug APK يكون موقعًا بمفتاح debug تلقائيًا، لذلك يصلح للاختبار والتثبيت المباشر عادةً.

ملاحظة: التعديل يعتمد على بنية OpenNavBar الحالية؛ إذا تغيرت أسماء الدوال في المصدر قد يحتاج patch إلى تحديث.
