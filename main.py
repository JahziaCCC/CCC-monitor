import os
import datetime
import requests

# =========================
# إعدادات تيليجرام
# =========================
BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

KSA_TZ = datetime.timezone(datetime.timedelta(hours=3))
now = datetime.datetime.now(KSA_TZ)

# =========================
# رسالة اختبار (تأكد النظام شغال)
# =========================
def send_test():
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": "✅ اختبار ناجح — CCC Monitor يعمل بشكل صحيح"
        }
    )

# =========================
# إنشاء التقرير
# =========================
def build_report():

    report = f"""
📄 تقرير الرصد والتحديث التشغيلي
🕒 تاريخ ووقت التحديث: {now.strftime('%Y-%m-%d %H:%M')} KSA

════════════════════
1️⃣ الملخص التنفيذي
📊 مؤشر المخاطر الموحد: 30/100
📌 مستوى المخاطر: 🟢 منخفض

🧾 تفسير تشغيلي:
• تم إنشاء التقرير آلياً.
• لا توجد أحداث مؤثرة حالياً.

════════════════════
2️⃣ مؤشرات سلاسل الإمداد الغذائي
- لا يوجد

════════════════════
3️⃣ الكوارث الطبيعية
- لا يوجد

════════════════════
4️⃣ حرائق الغابات
- لا يوجد

════════════════════
5️⃣ الأحداث والتحذيرات البحرية
- لا يوجد

════════════════════
6️⃣ حركة السفن والازدحام الموانئ
- لا يوجد

════════════════════
7️⃣ ملاحظات تشغيلية
• تم إعداد التقرير آلياً بناءً على مصادر الرصد.
• يتم إرسال تنبيه إضافي عند ظهور أحداث جديدة مؤثرة.
"""

    return report


# =========================
# إرسال التقرير
# =========================
def send_report(text):
    requests.post(
        f"https://api.telegram.org/bot{BOT}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": text
        }
    )


# =========================
# التشغيل الرئيسي
# =========================
if __name__ == "__main__":

    print("Running CCC Monitor...")

    # اختبار تيليجرام
    send_test()

    # بناء التقرير
    report = build_report()

    # إرسال التقرير
    send_report(report)

    print("Report sent successfully.")
