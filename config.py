# -*- coding: utf-8 -*-
"""ไฟล์ตั้งค่าบอท Discord MP3
ดึงค่า TOKEN จาก Environment Variable (เหมาะกับ Render)
"""

import os

# ===================== CONFIG =====================

# ดึง TOKEN จาก Environment Variable บน Render
TOKEN: str = os.getenv("DISCORD_TOKEN", "").strip()

if not TOKEN:
    raise SystemExit("❌ ERROR: ไม่พบค่า DISCORD_TOKEN ใน Environment ของ Render")

# รายการห้อง (Text Channel ID) ที่ให้ระบบลบข้อความอัตโนมัติทำงาน
TARGET_CHANNEL_IDS: set[int] = {1440191545251860594}

# ห้องที่อนุญาตให้ใช้คำสั่งดาวน์โหลด mp3 (!ytmp3 / /ytmp3)
YTMP3_ALLOWED_CHANNEL_IDS: set[int] = {1440191545251860594}

# OWNER / ADMIN ของบอท (User ID)
OWNER_IDS: set[int] = {1147798918973898762}
ADMIN_IDS: set[int] = set()

# เวลาลบข้อความอัตโนมัติ (วินาที)
AUTO_DELETE_DEFAULT_DELAY: int = 10
