# keep_alive.py
# เว็บเล็กๆ สำหรับให้ Render ใช้เช็คว่า service ยังไม่ดับ

import os
from threading import Thread
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Discord MP3 bot is running.", 200

def _run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    """เรียกฟังก์ชันนี้ก่อน bot.run() เพื่อให้ Flask รันในอีก thread"""
    t = Thread(target=_run, daemon=True)
    t.start()
