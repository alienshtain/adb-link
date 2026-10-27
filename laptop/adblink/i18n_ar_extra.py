"""Arabic for texts added after the first translation round (Modern Standard Arabic)."""
AR = {
    # tabs, sections
    "Phone app link": "ربط تطبيق الهاتف",
    "Information and controls of the phone": "معلومات الهاتف وأدوات التحكم به",
    "Connect the ADB Link app on the phone to this computer": "ربط تطبيق ADB Link على الهاتف بهذا الحاسوب",
    "Devices and adb setup": "الأجهزة وإعداد adb",
    "Show the connected phones and prepare adb": "عرض الهواتف المتصلة وتجهيز adb",
    "On the phone": "على الهاتف",
    "Commands that act on the phone": "أوامر تُنفَّذ على الهاتف",
    # settings
    "Icon in the system tray": "أيقونة في شريط النظام",
    "A small icon (like Discord): click it to open ADB Link or quit.":
        "أيقونة صغيرة (مثل Discord): اضغط عليها لفتح ADB Link أو لإغلاقه.",
    "Saved files": "الملفات المحفوظة",
    "Everything ADB Link saves on this computer goes here: files from the phone, screenshots, recordings and saved apps.":
        "كل ما يحفظه ADB Link على هذا الحاسوب يوضع هنا: ملفات الهاتف ولقطات الشاشة والتسجيلات والتطبيقات المحفوظة.",
    "Folder": "المجلد",
    "Change": "تغيير",
    "Open": "فتح",
    "Back to Documents/ADB Link": "العودة إلى Documents/ADB Link",
    "Language": "اللغة",
    "Language of ADB Link": "لغة ADB Link",
    "Restart to apply the change.": "أعد التشغيل لتطبيق التغيير.",
    "Restart now": "إعادة التشغيل الآن",
    "Open ADB Link": "فتح ADB Link",
    "Quit": "إغلاق",
    # files and previews
    "Save a copy on this computer": "حفظ نسخة على هذا الحاسوب",
    "Open with the default app": "فتح بالتطبيق الافتراضي",
    "Previous": "السابق",
    "Next": "التالي",
    "Double-click a folder to open it, or a picture / text file to preview it. Drag files here to upload.":
        "انقر مرتين على مجلد لفتحه، أو على صورة أو فيديو أو ملف نصي لمعاينته. اسحب الملفات إلى هنا لرفعها.",
    "No preview for this type. Select it and press Download.":
        "لا توجد معاينة لهذا النوع. حدده ثم اضغط «تنزيل».",
    "This picture format cannot be shown here. Use \"Open with the default app\".":
        "لا يمكن عرض هذه الصيغة هنا. استخدم «فتح بالتطبيق الافتراضي».",
    "Could not read the file": "تعذّرت قراءة الملف",
    # commands
    "Text to type": "النص المراد كتابته",
    "Copies a file or folder from the phone to Documents/ADB Link/Phone files on your computer.":
        "ينسخ ملفاً أو مجلداً من الهاتف إلى Documents/ADB Link/Phone files على حاسوبك.",
    "Saves a screenshot of the phone in Documents/ADB Link/Screenshots.":
        "يحفظ لقطة شاشة للهاتف في Documents/ADB Link/Screenshots.",
    "Records the screen for the given seconds (max 180), then saves the video in Documents/ADB Link/Recordings.":
        "يسجّل الشاشة للثواني المحددة (180 كحد أقصى) ثم يحفظ الفيديو في Documents/ADB Link/Recordings.",
    "Types text into the focused field on the phone. Arabic and other languages work too.":
        "يكتب نصاً في الحقل المحدد على الهاتف، ويدعم العربية وسائر اللغات.",
    # phone panel
    "Confirm on the phone screen": "أكّد من شاشة الهاتف",
    "The phone did not allow this change": "لم يسمح الهاتف بهذا التغيير",
    # typing
    "Typed on the phone.": "تمت الكتابة على الهاتف.",
    "Nothing to type.": "لا يوجد نص للكتابة.",
    "Typing Arabic needs the ADB Link app on the phone (run:  adblink install-phone) or the ADB Keyboard app.":
        "تحتاج الكتابة بالعربية إلى تطبيق ADB Link على الهاتف (شغّل:  adblink install-phone) أو إلى تطبيق ADB Keyboard.",
    "Needs xclip or wl-clipboard": "يحتاج إلى xclip أو wl-clipboard",
    "This file is": "حجم هذا الملف",
}

AR.update({
    "Automatic": "تلقائي",
    "Ready. Press Connect to link a phone, then use the pages above.":
        "جاهز. اضغط «اتصال» لربط هاتف، ثم استخدم الصفحات في الأعلى.",
    "Error": "خطأ",
    "In call": "في مكالمة",
})

PATTERNS = [
    (r"^(.+) and (\d+) more$", "{0} و{1} أخرى"),
    (r"^Downloaded (\d+) item\(s\) to (.+)$", "تم تنزيل العناصر ({0}) إلى {1}"),
    (r"^Sent (\d+) item\(s\) to (.+)$", "تم إرسال العناصر ({0}) إلى {1}"),
    (r"^Deleted (\d+) item\(s\)$", "تم حذف العناصر ({0})"),
    (r"^(\d+) seconds ago$", "منذ {0} ث"),
    (r"^(\d+) minutes ago$", "منذ {0} د"),
    (r"^(\d+) hours ago$", "منذ {0} س"),
    (r"^Last seen (.+)$", "آخر ظهور: {0}"),
    (r"^Installing (.+)$", "جارٍ تثبيت {0}"),
    (r"^Downloading (.+)$", "جارٍ تنزيل {0}"),
    (r"^Calling (.+)$", "جارٍ الاتصال بـ {0}"),
    (r"^SMS to (.+)$", "رسالة نصية إلى {0}"),
    (r"^Missing helper tools: (.+)$", "أدوات مساعدة ناقصة: {0}"),
    (r"^Connecting to (.+)$", "جارٍ الاتصال بـ {0}"),
    (r"^Brightness (\d+)%$", "السطوع {0}%"),
    (r"^This file is (.+)\. Download it instead \(button above\)\.$",
     "حجم هذا الملف {0}. نزّله بدلاً من ذلك (الزر في الأعلى)."),
    (r"^Saved to (.+)$", "تم الحفظ في {0}"),
    (r"^(.+?): on$", "{0}: مفعّل"),
    (r"^(.+?): off$", "{0}: متوقف"),
]
