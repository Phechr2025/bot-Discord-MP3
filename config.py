# -*- coding: utf-8 -*-
"""ไฟล์ตั้งค่าบอท Discord MP3

แก้ไขค่าต่าง ๆ ในไฟล์นี้เท่านั้น ไม่ต้องไปแก้ใน bot.py / form_view.py
แล้วค่อยรันบอทด้วยคำสั่ง::

    python3 bot.py
"""

# ===================== CONFIG สำหรับแก้ไขค่าตั้งต่าง ๆ =====================

# โทเคนบอท Discord
TOKEN: str = "MTQyMDA3MzA2MzE2ODM0NDA4NA.GgEf6L.IZrQ9TLcmOxD1eUu7d4zhfK7iqNj5xqwkviKJM"

# รายการห้อง (Text Channel ID) ที่ให้ระบบลบข้อความอัตโนมัติทำงาน
# ตัวอย่าง:
# TARGET_CHANNEL_IDS: set[int] = {123456789012345678, 987654321098765432}
TARGET_CHANNEL_IDS: set[int] = {1440191545251860594}

# รายการห้องที่อนุญาตให้ใช้คำสั่งดาวน์โหลด mp3 (!ytmp3 / /ytmp3)
# ถ้าเว้นว่างไว้ (set() ว่าง) = อนุญาตทุกห้อง
YTMP3_ALLOWED_CHANNEL_IDS: set[int] = {1440191545251860594}

# OWNER / ADMIN ของบอท (ใส่เป็น user ID)
# - OWNER_IDS: เจ้าของหลักของบอท (มีสิทธิ์ทุกอย่าง)
# - ADMIN_IDS: แอดมินของบอท (ใช้คำสั่งแอดมินได้)
OWNER_IDS: set[int] = {1147798918973898762}
ADMIN_IDS: set[int] = set()

# ค่าเริ่มต้นเวลา (วินาที) ให้ระบบลบข้อความอัตโนมัติ
AUTO_DELETE_DEFAULT_DELAY: int = 10
