import os
import json
import time
from websocket import create_connection

def main():
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if not key:
        print("❌ AISSTREAM_API_KEY غير موجود في Environment (Secret غير واصل للـWorkflow).")
        return

    print("✅ AISSTREAM_API_KEY موجود (لن يتم عرض المفتاح).")
    print(f"ℹ️ طول المفتاح: {len(key)}")

    # اشتراك بسيط جدًا لمدة 20 ثانية في نطاق جدة فقط لاختبار وصول الرسائل
    subscription = {
        "APIKey": key,
        "BoundingBoxes": [
            [[20.8, 38.5], [22.2, 40.2]]  # حول جدة تقريبًا
        ],
        "FilterMessageTypes": [
            "PositionReport",
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport"
        ]
    }

    try:
        ws = create_connection("wss://stream.aisstream.io/v0/stream", timeout=40)
        ws.send(json.dumps(subscription))
        print("✅ تم إرسال الاشتراك إلى AISStream. ننتظر رسائل لمدة 20 ثانية...")

        t0 = time.time()
        total = 0
        types = {}

        while time.time() - t0 < 20:
            raw = ws.recv()
            if not raw:
                continue
            total += 1
            try:
                msg = json.loads(raw)
            except Exception:
                types["<non-json>"] = types.get("<non-json>", 0) + 1
                continue

            mt = msg.get("MessageType") or msg.get("messageType") or "<no-MessageType>"
            types[mt] = types.get(mt, 0) + 1

        ws.close()
        print(f"📦 عدد الرسائل المستلمة: {total}")
        print("📌 توزيع MessageType:")
        for k, v in sorted(types.items(), key=lambda x: -x[1])[:20]:
            print(f" - {k}: {v}")

        if total == 0:
            print("⚠️ لم نستلم أي رسائل خلال 20 ثانية (قد يكون حجب WebSocket في GitHub runner أو مشكلة خدمة/مفتاح).")

    except Exception as e:
        print("❌ فشل الاتصال/الاستقبال من AISStream:")
        print(type(e).__name__, str(e))

if __name__ == "__main__":
    main()
