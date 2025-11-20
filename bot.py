# -*- coding: utf-8 -*-
import asyncio
import os
import tempfile
from typing import Optional, Set, Dict, Callable, Awaitable, Any

import discord
from discord.ext import commands
from discord import app_commands

from config import (
    TOKEN,
    TARGET_CHANNEL_IDS,
    YTMP3_ALLOWED_CHANNEL_IDS,
    OWNER_IDS,
    ADMIN_IDS,
    AUTO_DELETE_DEFAULT_DELAY,
)
from form_view import YTMP3View, build_form_embed
from keep_alive import keep_alive

# ----------------- ตัวแปรสถานะในหน่วยความจำ -----------------

AUTO_DELETE_ENABLED: bool = False
AUTO_DELETE_DELAY: int = AUTO_DELETE_DEFAULT_DELAY
EXEMPT_MESSAGE_IDS: Set[int] = set()  # id ข้อความที่ "ยกเว้นไม่ลบ"

# เก็บสถานะรอชื่อไฟล์ จากคำสั่ง ytmp3 (ข้อความปกติ / slash)
# key = user.id, value = url ที่จะโหลด
PENDING_URL_BY_USER: Dict[int, str] = {}

# คิวดาวน์โหลด (ให้ทำทีละ 1 งาน)
DOWNLOAD_QUEUE: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
CURRENT_JOB: Optional[Dict[str, Any]] = None
CURRENT_DOWNLOAD_TASK: Optional[asyncio.Task] = None
JOB_COUNTER: int = 0

MAX_FILE_SIZE_BYTES: int = 30 * 1024 * 1024  # จำกัดไฟล์สูงสุด 30 MB


# ----------------- ฟังก์ชันช่วยต่าง ๆ -----------------


def is_owner(user: discord.abc.User) -> bool:
    return user.id in OWNER_IDS


def is_admin(user: discord.abc.User) -> bool:
    return user.id in ADMIN_IDS or is_owner(user)


def get_queue_status_text() -> str:
    """ส่งข้อความสถานะคิวดาวน์โหลด"""
    running = CURRENT_JOB is not None and CURRENT_DOWNLOAD_TASK is not None and not CURRENT_DOWNLOAD_TASK.done()
    waiting = DOWNLOAD_QUEUE.qsize()
    if not running and waiting == 0:
        return "✅ คิวว่าง ไม่มีงานดาวน์โหลดค้างอยู่"
    lines = ["📊 สถานะคิวดาวน์โหลด:"]
    if running:
        lines.append("• กำลังดาวน์โหลดอยู่ 1 งาน")
    if waiting:
        lines.append(f"• รอในคิวอีก {waiting} งาน")
    return "\n".join(lines)


async def download_mp3(url: str, custom_name: Optional[str]) -> str:
    """โหลดและแปลง YouTube เป็น MP3 แล้วคืน path ไฟล์ชั่วคราวกลับมา"""
    import yt_dlp  # นำเข้าในฟังก์ชัน เพื่อลดโอกาส import error ตอนยังไม่ติดตั้ง

    temp_dir = tempfile.mkdtemp(prefix="ytmp3_")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(temp_dir, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title", "audio")
        original_path = ydl.prepare_filename(info)
        base, _ext = os.path.splitext(original_path)
        mp3_path = base + ".mp3"

    # ถ้าผู้ใช้ตั้งชื่อเอง -> เปลี่ยนชื่อไฟล์
    if custom_name:
        safe_name = custom_name.replace("/", "_").replace("\\", "_").strip() or title
        new_path = os.path.join(temp_dir, safe_name + ".mp3")
        os.replace(mp3_path, new_path)
        mp3_path = new_path

    return mp3_path


async def _cleanup_temp(mp3_path: Optional[str]) -> None:
    if not mp3_path or not os.path.isfile(mp3_path):
        return
    try:
        temp_root = os.path.dirname(mp3_path)
        for name in os.listdir(temp_root):
            try:
                os.remove(os.path.join(temp_root, name))
            except OSError:
                pass
        os.rmdir(temp_root)
    except OSError:
        pass


async def process_download_job(job: Dict[str, Any]) -> None:
    """ประมวลผลงานดาวน์โหลด 1 งาน (รันจาก worker เท่านั้น)"""
    user: discord.User = job["user"]
    url: str = job["url"]
    custom_name: Optional[str] = job["custom_name"]

    dm = await user.create_dm()
    status_msg = await dm.send("⏳ กำลังดาวน์โหลดและแปลงเป็น MP3...")
    mp3_path: Optional[str] = None

    try:
        mp3_path = await download_mp3(url, custom_name)
        file_size = os.path.getsize(mp3_path)

        if file_size > MAX_FILE_SIZE_BYTES:
            await status_msg.edit(
                content="⚠️ ไฟล์นี้มีขนาดเกิน 30 MB ไม่สามารถส่งผ่าน Discord ได้"
            )
        else:
            await status_msg.edit(content="✅ โหลดเสร็จแล้ว ส่งไฟล์ให้แล้วครับ")
            await dm.send(file=discord.File(mp3_path, filename=os.path.basename(mp3_path)))
    except asyncio.CancelledError:
        # ถูกยกเลิกโดยแอดมิน
        try:
            await status_msg.edit(content="⛔ งานดาวน์โหลดนี้ถูกยกเลิกโดยแอดมิน")
        except discord.HTTPException:
            pass
        raise
    except Exception as e:
        try:
            await status_msg.edit(content=f"❌ เกิดข้อผิดพลาด: {e}")
        except discord.HTTPException:
            pass
    finally:
        await _cleanup_temp(mp3_path)


async def download_worker() -> None:
    """ลูป worker สำหรับประมวลผลงานในคิว ทำทีละ 1 งาน"""
    global CURRENT_JOB, CURRENT_DOWNLOAD_TASK
    while True:
        job = await DOWNLOAD_QUEUE.get()
        CURRENT_JOB = job
        CURRENT_DOWNLOAD_TASK = asyncio.create_task(process_download_job(job))
        try:
            await CURRENT_DOWNLOAD_TASK
        except asyncio.CancelledError:
            # แค่ข้ามไปงานถัดไป
            pass
        finally:
            CURRENT_DOWNLOAD_TASK = None
            CURRENT_JOB = None
            DOWNLOAD_QUEUE.task_done()


async def enqueue_download(user: discord.User, url: str, custom_name: Optional[str]) -> int:
    """เพิ่มงานดาวน์โหลดเข้า queue และคืนลำดับคิว (รวมงานที่กำลังทำอยู่)"""
    global JOB_COUNTER
    JOB_COUNTER += 1
    job = {
        "id": JOB_COUNTER,
        "user": user,
        "url": url,
        "custom_name": custom_name,
    }

    running = CURRENT_JOB is not None and CURRENT_DOWNLOAD_TASK is not None and not CURRENT_DOWNLOAD_TASK.done()
    queued_before = DOWNLOAD_QUEUE.qsize()

    await DOWNLOAD_QUEUE.put(job)

    # position รวม (งานที่กำลังทำอยู่ + ที่รอก่อนหน้า + งานของตัวเอง)
    position = (1 if running else 0) + queued_before + 1
    return position


async def schedule_auto_delete(message: discord.Message):
    """ตั้งเวลาลบข้อความ (ถ้าเปิดระบบ autodel และห้องอยู่ในลิสต์)"""
    if isinstance(message.channel, discord.DMChannel):
        return
    if not AUTO_DELETE_ENABLED:
        return
    if TARGET_CHANNEL_IDS and message.channel.id not in TARGET_CHANNEL_IDS:
        return
    if message.id in EXEMPT_MESSAGE_IDS:
        return
    if message.author.bot:
        return

    await asyncio.sleep(max(1, AUTO_DELETE_DELAY))

    # เช็คอีกที เผื่อระหว่างนั้นมีเปลี่ยนสถานะ
    if AUTO_DELETE_ENABLED and message.id not in EXEMPT_MESSAGE_IDS:
        try:
            await message.delete()
        except discord.HTTPException:
            pass


def _check_ytmp3_channel(channel) -> bool:
    """ตรวจว่าห้องนี้อนุญาตให้ใช้คำสั่งดาวน์โหลด mp3 หรือไม่"""
    if not YTMP3_ALLOWED_CHANNEL_IDS:
        return True
    ch_id = getattr(channel, "id", None)
    return ch_id in YTMP3_ALLOWED_CHANNEL_IDS


# ----------------- สร้างบอท -----------------

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    # ซิงค์ slash commands
    try:
        await bot.tree.sync()
        print("ซิงค์ slash commands แล้ว")
    except Exception as e:
        print("Sync slash command error:", e)
    print(f"ล็อกอินเป็น {bot.user} (ID: {bot.user.id})")

    # เริ่ม worker ถ้ายังไม่เริ่ม
    if not hasattr(bot, "_ytmp3_worker_started"):
        bot._ytmp3_worker_started = True
        bot.loop.create_task(download_worker())
        print("เริ่ม download_worker แล้ว")


@bot.event
async def on_message(message: discord.Message):
    # ตั้งเวลาลบ (ถ้าเปิด autodel)
    if not isinstance(message.channel, discord.DMChannel):
        bot.loop.create_task(schedule_auto_delete(message))

    # ให้ระบบ command ทำงาน
    await bot.process_commands(message)

    # จัดการกับข้อความจากผู้ใช้ที่กำลังรอชื่อไฟล์อยู่
    if message.author.bot:
        return

    user_id = message.author.id
    if user_id in PENDING_URL_BY_USER:
        url = PENDING_URL_BY_USER.pop(user_id)
        file_name_raw = message.content.strip()

        if file_name_raw.lower() == "no":
            custom_name = None
        else:
            custom_name = file_name_raw or None

        position = await enqueue_download(message.author, url, custom_name)

        if position == 1:
            text = (
                "🟢 คิวว่าง กำลังเริ่มดาวน์โหลดให้คุณทันที\n"
                "เดี๋ยวผมจะส่งไฟล์ MP3 ให้ทาง DM เมื่อโหลดเสร็จครับ"
            )
        else:
            text = (
                f"⏳ เพิ่มงานของคุณเข้าคิวแล้ว (ลำดับที่ {position})\n"
                f"ตอนนี้มีงานก่อนหน้าคุณ {position - 1} งาน เดี๋ยวผมจะส่งไฟล์ MP3 ให้ทาง DM เมื่อถึงคิวครับ"
            )

        await message.channel.send(text, reference=message)


# ----------------- คำสั่งสำหรับดาวน์โหลด MP3 (Hybrid: ใช้ได้ทั้ง ! และ /) -----------------


@bot.hybrid_command(name="ytmp3", description="ดาวน์โหลด YouTube เป็นไฟล์ MP3 และส่งทาง DM (มีคิว)")
@app_commands.describe(url="ลิงก์ YouTube (เฉพาะวิดีโอเดี่ยว ไม่ใช่เพลย์ลิสต์)")
async def ytmp3(ctx: commands.Context, url: str):
    """ใช้ได้ทั้ง !ytmp3 และ /ytmp3"""
    if ctx.guild and not _check_ytmp3_channel(ctx.channel):
        await ctx.reply("❌ ห้องนี้ไม่ได้รับอนุญาตให้ใช้คำสั่งดาวน์โหลด mp3")
        return

    PENDING_URL_BY_USER[ctx.author.id] = url

    # ถ้าใช้ใน DM ก็ถามใน DM เลย
    if isinstance(ctx.channel, discord.DMChannel):
        await ctx.send(
            "ต้องการตั้งชื่อไฟล์ว่าอะไร?\nพิมพ์ **No** เพื่อใช้ชื่อต้นฉบับจาก YouTube"
        )
        return

    # ถ้าใช้ในเซิร์ฟเวอร์ -> พยายามไปถามต่อใน DM
    try:
        dm = await ctx.author.create_dm()
        await dm.send(
            "คุณใช้คำสั่ง ytmp3\n"
            "กรุณาพิมพ์ชื่อไฟล์ที่ต้องการตั้ง\n"
            "พิมพ์ **No** เพื่อใช้ชื่อต้นฉบับจาก YouTube"
        )
        await ctx.reply("ผมส่ง DM ไปถามชื่อไฟล์แล้วนะครับ ถ้าไม่เห็นให้เช็คว่าเปิดรับ DM จากเซิร์ฟเวอร์นี้หรือยัง")
    except discord.HTTPException:
        # ถ้า DM ไม่ได้ ก็ถามในห้องเดิม
        await ctx.reply(
            "ไม่สามารถส่ง DM ถึงคุณได้ กรุณาพิมพ์ชื่อไฟล์ที่ต้องการตั้งในห้องนี้\n"
            "และพิมพ์ **No** เพื่อใช้ชื่อต้นฉบับจาก YouTube",
            mention_author=True,
        )


# ----------------- ส่วนของแบบฟอร์มการ์ด + ปุ่มแปลงเป็น MP3 -----------------


async def handle_form_submit(interaction: discord.Interaction, url: str, filename: str):
    """callback ตอนผู้ใช้กรอกแบบฟอร์มเสร็จใน modal"""
    url = url.strip()
    filename = filename.strip()

    if not url:
        await interaction.response.send_message("❌ กรุณาใส่ URL YouTube", ephemeral=True)
        return

    if "youtu" not in url.lower():
        await interaction.response.send_message("❌ URL ต้องเป็นของ YouTube เท่านั้น", ephemeral=True)
        return

    if filename.lower() == "no":
        custom_name = None
    else:
        custom_name = filename or None

    position = await enqueue_download(interaction.user, url, custom_name)

    if position == 1:
        msg = (
            "🟢 คิวว่าง กำลังเริ่มดาวน์โหลดให้คุณทันที\n"
            "เดี๋ยวผมจะส่งไฟล์ MP3 ให้ทาง DM เมื่อโหลดเสร็จครับ"
        )
    else:
        msg = (
            f"⏳ เพิ่มงานของคุณเข้าคิวแล้ว (ลำดับที่ {position})\n"
            f"ตอนนี้มีงานก่อนหน้าคุณ {position - 1} งาน เดี๋ยวผมจะส่งไฟล์ MP3 ให้ทาง DM เมื่อถึงคิวครับ"
        )

    await interaction.response.send_message(msg, ephemeral=True)


@bot.hybrid_command(
    name="ytmp3_form",
    description="สร้างการ์ดแบบฟอร์มให้คนกดปุ่มแปลงเป็น MP3 (มีปุ่มเช็คคิว)",
)
@app_commands.describe(
    title="หัวข้อบนการ์ด (เช่น 'mp3')",
    description="รายละเอียดใต้หัวข้อ",
    image_url="ลิงก์รูป (ไม่ใส่ก็ได้)",
)
async def ytmp3_form(
    ctx: commands.Context,
    title: str = "mp3",
    description: str = "ดาวน์โหลด mp3",
    image_url: Optional[str] = None,
):
    """สร้าง embed + ปุ่มสำหรับเรียกแบบฟอร์ม (เฉพาะแอดมิน)"""
    if not is_admin(ctx.author):
        await ctx.reply("❌ คำสั่งนี้ใช้ได้เฉพาะแอดมินเท่านั้น")
        return

    embed = build_form_embed(title=title, description=description, image_url=image_url)
    view = YTMP3View(on_submit=handle_form_submit, get_queue_text=get_queue_status_text)

    await ctx.reply("แบบฟอร์ม:", embed=embed, view=view)


# ----------------- คำสั่งเช็คคิวดาวน์โหลด -----------------


@bot.hybrid_command(name="queue_status", description="เช็คสถานะคิวดาวน์โหลด MP3")
async def queue_status(ctx: commands.Context):
    text = get_queue_status_text()
    await ctx.reply(text)


# ----------------- คำสั่งจัดการระบบลบข้อความอัตโนมัติ -----------------


@bot.hybrid_command(name="autodel", description="เปิด/ปิดระบบลบข้อความอัตโนมัติในห้องที่กำหนด")
@app_commands.describe(mode="พิมพ์ on หรือ off")
async def autodel(ctx: commands.Context, mode: str):
    global AUTO_DELETE_ENABLED
    if not is_admin(ctx.author):
        await ctx.reply("❌ คำสั่งนี้ใช้ได้เฉพาะแอดมินเท่านั้น")
        return

    mode = mode.lower()
    if mode == "on":
        AUTO_DELETE_ENABLED = True
        await ctx.reply(
            f"✅ เปิดระบบลบข้อความอัตโนมัติแล้ว (ลบหลัง {AUTO_DELETE_DELAY} วินาที)"
        )
    elif mode == "off":
        AUTO_DELETE_ENABLED = False
        await ctx.reply("🟧 ปิดระบบลบข้อความอัตโนมัติแล้ว")
    else:
        await ctx.reply("❌ ให้ใช้คำว่า on หรือ off เท่านั้น")


@bot.hybrid_command(name="autodel_delay", description="ตั้งเวลา (วินาที) ที่ให้ระบบลบข้อความอัตโนมัติ")
@app_commands.describe(seconds="จำนวนวินาที (ต้องปิด autodel ก่อนถึงจะตั้งได้)")
async def autodel_delay(ctx: commands.Context, seconds: int):
    global AUTO_DELETE_DELAY
    if not is_admin(ctx.author):
        await ctx.reply("❌ คำสั่งนี้ใช้ได้เฉพาะแอดมินเท่านั้น")
        return

    if AUTO_DELETE_ENABLED:
        await ctx.reply(
            "❌ กรุณาปิดระบบ autodel ด้วยคำสั่ง /autodel off ก่อน แล้วค่อยตั้งเวลาใหม่"
        )
        return

    if seconds < 1 or seconds > 3600:
        await ctx.reply("❌ กรุณาใส่ค่า 1–3600 วินาที")
        return

    AUTO_DELETE_DELAY = seconds
    await ctx.reply(f"✅ ตั้งเวลา autodel เป็น {seconds} วินาทีแล้ว")


@bot.hybrid_command(name="autodel_exempt_add", description="เพิ่มข้อความเข้า list ยกเว้นไม่ให้โดนลบ (ตาม ID)")
@app_commands.describe(message_id="ID ของข้อความ")
async def autodel_exempt_add(ctx: commands.Context, message_id: int):
    if not is_admin(ctx.author):
        await ctx.reply("❌ คำสั่งนี้ใช้ได้เฉพาะแอดมินเท่านั้น")
        return

    EXEMPT_MESSAGE_IDS.add(message_id)
    await ctx.reply(f"✅ เพิ่มข้อความ ID `{message_id}` เข้า list ยกเว้นแล้ว")


@bot.hybrid_command(name="autodel_exempt_remove", description="เอาข้อความออกจาก list ยกเว้น (ตาม ID)")
@app_commands.describe(message_id="ID ของข้อความ")
async def autodel_exempt_remove(ctx: commands.Context, message_id: int):
    if not is_admin(ctx.author):
        await ctx.reply("❌ คำสั่งนี้ใช้ได้เฉพาะแอดมินเท่านั้น")
        return

    if message_id in EXEMPT_MESSAGE_IDS:
        EXEMPT_MESSAGE_IDS.remove(message_id)
        await ctx.reply(f"✅ ลบข้อความ ID `{message_id}` ออกจาก list ยกเว้นแล้ว")
    else:
        await ctx.reply("❌ ไม่พบข้อความ ID นี้ใน list ยกเว้น")


# ----------------- คำสั่งจัดการแอดมิน (สำหรับ OWNER เท่านั้น) -----------------


@bot.hybrid_command(name="add_admin", description="เพิ่มแอดมินบอท (OWNER เท่านั้น)")
@app_commands.describe(user_id="ID ผู้ใช้ที่ต้องการเพิ่มเป็นแอดมิน")
async def add_admin(ctx: commands.Context, user_id: int):
    if not is_owner(ctx.author):
        await ctx.reply("❌ คำสั่งนี้ใช้ได้เฉพาะ OWNER เท่านั้น")
        return

    ADMIN_IDS.add(user_id)
    await ctx.reply(f"✅ เพิ่ม `<@{user_id}>` เป็นแอดมินแล้ว")


@bot.hybrid_command(name="remove_admin", description="ลบแอดมินบอท (OWNER เท่านั้น)")
@app_commands.describe(user_id="ID ผู้ใช้ที่ต้องการลบออกจากแอดมิน")
async def remove_admin(ctx: commands.Context, user_id: int):
    if not is_owner(ctx.author):
        await ctx.reply("❌ คำสั่งนี้ใช้ได้เฉพาะ OWNER เท่านั้น")
        return

    if user_id in ADMIN_IDS:
        ADMIN_IDS.remove(user_id)
        await ctx.reply(f"✅ เอา `<@{user_id}>` ออกจากแอดมินแล้ว")
    else:
        await ctx.reply("❌ ผู้ใช้นี้ไม่ได้เป็นแอดมินอยู่แล้ว")


# ----------------- คำสั่งยกเลิกงานดาวน์โหลดทั้งหมด (สำหรับแอดมิน) -----------------


@bot.hybrid_command(
    name="cancel_downloads",
    description="ยกเลิกงานดาวน์โหลด MP3 ที่กำลังทำอยู่และล้างคิวทั้งหมด (แอดมิน)",
)
async def cancel_downloads(ctx: commands.Context):
    global CURRENT_DOWNLOAD_TASK

    if not is_admin(ctx.author):
        await ctx.reply("❌ คำสั่งนี้ใช้ได้เฉพาะแอดมินเท่านั้น")
        return

    # ล้างคิวรอ
    cancelled_in_queue = 0
    try:
        while True:
            DOWNLOAD_QUEUE.get_nowait()
            DOWNLOAD_QUEUE.task_done()
            cancelled_in_queue += 1
    except asyncio.QueueEmpty:
        pass

    # ยกเลิกงานที่กำลังทำอยู่ (ถ้ามี)
    if CURRENT_DOWNLOAD_TASK and not CURRENT_DOWNLOAD_TASK.done():
        CURRENT_DOWNLOAD_TASK.cancel()

    msg_parts = ["✅ ยกเลิกงานดาวน์โหลดทั้งหมดแล้ว"]
    if cancelled_in_queue:
        msg_parts.append(f"(ลบจากคิวรอ {cancelled_in_queue} งาน)")

    await ctx.reply(" ".join(msg_parts))


# ----------------- main -----------------

if __name__ == "__main__":
    if TOKEN == "PUT_YOUR_TOKEN_HERE":
        raise SystemExit("กรุณาแก้ไขไฟล์ config.py แล้วใส่ TOKEN ก่อนรันบอท")
    # รันเว็บเล็กๆ ด้วย Flask เพื่อให้ Render เช็คสถานะ Web Service
    keep_alive()
    # จากนั้นรันบอท Discord ตามปกติ
    bot.run(TOKEN)
