import os
import asyncio
import tempfile
import uuid

import discord
from discord.ext import commands
import yt_dlp

# ===================== การตั้งค่าเบื้องต้น =====================

# ใส่โทเคนบอท Discord ของคุณตรงนี้
TOKEN = "PUT_YOUR_TOKEN_HERE"

# รายการห้อง (Text Channel ID) ที่ให้ระบบลบข้อความอัตโนมัติทำงาน
# ใส่เป็น set ของตัวเลข เช่น {123456789012345678, 987654321098765432}
TARGET_CHANNEL_IDS: set[int] = set()

# รายการห้องที่อนุญาตให้ใช้คำสั่งดาวน์โหลด mp3 (!ytmp3 / /ytmp3)
# ถ้าเว้นว่างไว้ (set() ว่าง) = อนุญาตทุกห้อง
YTMP3_ALLOWED_CHANNEL_IDS: set[int] = set()

# ค่าเริ่มต้นของระบบลบข้อความอัตโนมัติ (False = ปิด, True = เปิด)
AUTO_DELETE_ENABLED: bool = False

# เวลาในการลบข้อความอัตโนมัติ (หน่วย: วินาที) ค่าเริ่มต้น = 10 วินาที
AUTO_DELETE_DELAY_SECONDS: int = 10

# เก็บ ID ของข้อความที่ "ไม่ต้องลบ" แม้ระบบ auto delete จะเปิดอยู่
EXEMPT_MESSAGE_IDS: set[int] = set()

# รายการ "คำ" หรือ "ข้อความ" ที่ถ้าพบในข้อความ จะทำให้เข้าข่ายลบอัตโนมัติ
# - ถ้าเซ็ตนี้ว่างเปล่า -> ลบ "ทุกข้อความ" ตามเงื่อนไขเดิม
# - ถ้าในนี้มีคำ -> จะลบเฉพาะข้อความที่มีคำใดคำหนึ่งในนี้ (ไม่สนตัวพิมพ์เล็ก/ใหญ่)
AUTO_DELETE_KEYWORDS: set[str] = set()

# ระบบแอดมินภายในบอท
# OWNER_IDS: แนะนำให้ใส่ ID ของเจ้าของบอท / เจ้าของเซิร์ฟเวอร์ที่ไว้ใจได้
OWNER_IDS: set[int] = set()
# ADMIN_IDS: แอดมินที่เพิ่มผ่านคำสั่ง /admin_add_id หรือ !admin_add_id
ADMIN_IDS: set[int] = set()

# เก็บสถานะ "รอผู้ใช้ตอบชื่อไฟล์" ต่อ user แต่ละคน: user_id -> url
pending_name: dict[int, str] = {}

# =============================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


# ---------------- ฟังก์ชันตรวจสอบสิทธิ์แอดมิน ----------------

def is_admin_user(user: discord.abc.User | discord.Member) -> bool:
    """เช็คว่า user เป็นแอดมินของบอทหรือไม่"""
    # ถ้าอยู่ใน OWNER_IDS → แอดมินแน่นอน
    if user.id in OWNER_IDS:
        return True

    # ถ้าอยู่ใน ADMIN_IDS → แอดมิน
    if user.id in ADMIN_IDS:
        return True

    # ถ้าเป็นสมาชิกในกิลด์ และมีสิทธิ์ Administrator → ถือว่าเป็นแอดมิน
    if isinstance(user, discord.Member):
        perms = user.guild_permissions
        if perms.administrator:
            return True

    return False


def admin_only():
    async def predicate(ctx: commands.Context):
        if is_admin_user(ctx.author):
            return True
        raise commands.CheckFailure("คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (เฉพาะแอดมินของบอท)")
    return commands.check(predicate)


# ---------------- ฟังก์ชันโหลดและแปลงเป็น MP3 ----------------

async def download_mp3(url: str, custom_name: str | None = None) -> str:
    """โหลดเสียงจาก YouTube แล้วแปลงเป็น mp3
    ถ้ามี custom_name -> ใช้ชื่อนั้น
    ถ้า custom_name = None -> ใช้ชื่อต้นฉบับจาก YouTube
    คืนค่า path ของไฟล์ mp3 ที่ได้
    """
    temp_dir = tempfile.mkdtemp(prefix="ytmp3_")

    def sanitize(name: str) -> str:
        bad = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for b in bad:
            name = name.replace(b, '_')
        return name.strip() or str(uuid.uuid4())

    if custom_name:
        outtmpl = os.path.join(temp_dir, sanitize(custom_name) + ".%(ext)s")
    else:
        # ใช้ชื่อต้นฉบับจาก YouTube
        outtmpl = os.path.join(temp_dir, "%(title)s.%(ext)s")

    opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }

    loop = asyncio.get_event_loop()

    def _run():
        with yt_dlp.YoutubeDL(opts) as y:
            y.download([url])

    await loop.run_in_executor(None, _run)

    files = [f for f in os.listdir(temp_dir) if f.lower().endswith(".mp3")]
    if not files:
        raise FileNotFoundError("ไม่พบไฟล์ mp3")

    return os.path.join(temp_dir, files[0])


# ---------------- คำสั่ง !ytmp3 / /ytmp3 (ทุกคนใช้ได้) ----------------

@bot.hybrid_command(name="ytmp3", description="ดาวน์โหลดไฟล์ mp3 จาก YouTube")
async def ytmp3(ctx: commands.Context, url: str):
    """คำสั่งดาวน์โหลด mp3 จาก YouTube: !ytmp3 <ลิงก์> หรือ /ytmp3"""
    # ตรวจว่าห้องนี้อนุญาตให้ใช้คำสั่งหรือไม่ (ยกเว้น DM)
    if not isinstance(ctx.channel, discord.DMChannel):
        if YTMP3_ALLOWED_CHANNEL_IDS and ctx.channel.id not in YTMP3_ALLOWED_CHANNEL_IDS:
            await ctx.reply("❌ ใช้คำสั่งนี้ได้เฉพาะในห้องที่กำหนดเท่านั้น")
            return

    pending_name[ctx.author.id] = url
    await ctx.reply(
        "ต้องการตั้งชื่อไฟล์ว่าอะไร?\n"
        "พิมพ์ **No** เพื่อใช้ชื่อต้นฉบับจาก YouTube"
    )


# ---------------- ระบบลบข้อความอัตโนมัติ ----------------

async def schedule_auto_delete(message: discord.Message) -> None:
    """รอ AUTO_DELETE_DELAY_SECONDS วินาที แล้วลบข้อความ ถ้าเข้าเงื่อนไข"""
    # ลบเฉพาะข้อความในเซิร์ฟเวอร์ (ไม่ลบ DM)
    if isinstance(message.channel, discord.DMChannel):
        return

    if not AUTO_DELETE_ENABLED:
        return

    # ถ้าระบุ TARGET_CHANNEL_IDS ไว้ ให้ลบเฉพาะช่องที่ระบุ
    if TARGET_CHANNEL_IDS and message.channel.id not in TARGET_CHANNEL_IDS:
        return

    # ยกเว้นข้อความที่กำหนดด้วย ID
    if message.id in EXEMPT_MESSAGE_IDS:
        return

    # ถ้ามีการตั้ง AUTO_DELETE_KEYWORDS ให้ทำงานเฉพาะข้อความที่มีคำพวกนั้น
    content = (message.content or "").lower()
    if AUTO_DELETE_KEYWORDS:
        if not any(keyword in content for keyword in AUTO_DELETE_KEYWORDS):
            return

    # รอเวลาตามที่ตั้งไว้ แล้วค่อยลบ
    await asyncio.sleep(max(1, int(AUTO_DELETE_DELAY_SECONDS)))

    try:
        await message.delete()
    except (discord.NotFound, discord.Forbidden):
        # ข้อความถูกลบไปแล้ว หรือไม่มีสิทธิ์
        return
    except Exception:
        return


async def cleanup_existing_messages() -> None:
    """ลบข้อความเก่าทั้งหมดในช่องที่กำหนด (ยกเว้นข้อความที่ถูกยกเว้น และไม่ตรง keyword ถ้ามีตั้งไว้)"""
    for guild in bot.guilds:
        for channel in guild.text_channels:
            # ถ้าระบุ TARGET_CHANNEL_IDS ไว้ ให้ทำเฉพาะช่องที่อยู่ในรายการ
            if TARGET_CHANNEL_IDS and channel.id not in TARGET_CHANNEL_IDS:
                continue

            try:
                async for msg in channel.history(limit=None):
                    if msg.id in EXEMPT_MESSAGE_IDS:
                        continue

                    content = (msg.content or "").lower()
                    if AUTO_DELETE_KEYWORDS:
                        if not any(keyword in content for keyword in AUTO_DELETE_KEYWORDS):
                            continue

                    try:
                        await msg.delete()
                    except (discord.NotFound, discord.Forbidden):
                        continue
                    except Exception:
                        continue
            except Exception:
                continue


# ---------------- คำสั่งแอดมิน: เปิด/ปิดระบบลบข้อความ ----------------

@bot.hybrid_command(name="autodel", description="เปิด/ปิดระบบลบข้อความอัตโนมัติ (แอดมิน)")
@admin_only()
async def autodel(ctx: commands.Context, mode: str | None = None):
    """เปิด/ปิดระบบลบข้อความอัตโนมัติ

    ใช้:
      !autodel          -> ดูสถานะ
      !autodel on       -> เปิดระบบ + ลบข้อความเก่าทั้งหมด (ยกเว้นที่ถูกยกเว้น)
      !autodel off      -> ปิดระบบ
    """
    global AUTO_DELETE_ENABLED

    if mode is None:
        status = "เปิด" if AUTO_DELETE_ENABLED else "ปิด"
        await ctx.reply(
            f"สถานะระบบลบข้อความอัตโนมัติ: {status}\n"
            f"เวลาลบปัจจุบัน: {AUTO_DELETE_DELAY_SECONDS} วินาที\n"
            f"จำนวนคำที่ใช้เป็นตัวกรอง: {len(AUTO_DELETE_KEYWORDS)} คำ"
        )
        return

    m = mode.lower()
    if m in ("on", "เปิด", "enable", "1"):
        AUTO_DELETE_ENABLED = True
        await ctx.reply(
            "✅ เปิดระบบลบข้อความอัตโนมัติแล้ว\n"
            f"จะลบข้อความหลังส่ง {AUTO_DELETE_DELAY_SECONDS} วินาที "
            "(เฉพาะห้องที่กำหนด และไม่รวมข้อความที่ยกเว้น)"
        )
        await cleanup_existing_messages()
        await ctx.send("✅ ลบข้อความเก่าเสร็จแล้ว", delete_after=5)
    elif m in ("off", "ปิด", "disable", "0"):
        AUTO_DELETE_ENABLED = False
        await ctx.reply("⏹ ปิดระบบลบข้อความอัตโนมัติแล้ว")
    else:
        await ctx.reply("ใช้คำสั่ง: `!autodel on` หรือ `!autodel off`")


@autodel.error
async def autodel_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        await ctx.reply("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (เฉพาะแอดมินของบอท)")


# ---------------- คำสั่งจัดการข้อความที่ยกเว้น (EXEMPT_MESSAGE_IDS) ----------------

@bot.hybrid_command(name="autodel_exempt_add", description="เพิ่มข้อความที่ไม่ต้องลบ (แอดมิน)")
@admin_only()
async def autodel_exempt_add(ctx: commands.Context, message_id: int):
    """เพิ่มข้อความที่ 'ไม่ต้องลบ' โดยใช้ message ID"""
    EXEMPT_MESSAGE_IDS.add(message_id)
    await ctx.reply(f"✅ เพิ่มข้อความ ID `{message_id}` เข้า list ยกเว้นแล้ว")


@bot.hybrid_command(name="autodel_exempt_remove", description="เอาข้อความออกจาก list ยกเว้น (แอดมิน)")
@admin_only()
async def autodel_exempt_remove(ctx: commands.Context, message_id: int):
    """เอาข้อความออกจาก list ยกเว้น โดยใช้ message ID"""
    if message_id in EXEMPT_MESSAGE_IDS:
        EXEMPT_MESSAGE_IDS.remove(message_id)
        await ctx.reply(f"✅ ลบข้อความ ID `{message_id}` ออกจาก list ยกเว้นแล้ว")
    else:
        await ctx.reply("❌ ไม่พบข้อความ ID นี้ใน list ยกเว้น")


# ---------------- คำสั่งจัดการ KEYWORDS สำหรับลบอัตโนมัติ ----------------

@bot.hybrid_command(name="autodel_word_add", description="เพิ่มคำสำหรับใช้กรองลบข้อความอัตโนมัติ (แอดมिन)")
@admin_only()
async def autodel_word_add(ctx: commands.Context, *, word: str):
    """เพิ่มคำที่จะใช้เป็นตัวกรองลบข้อความอัตโนมัติ
    ต้องปิดระบบลบข้อความอัตโนมัติก่อน (!autodel off)
    """
    if AUTO_DELETE_ENABLED:
        await ctx.reply("❌ กรุณาปิดระบบลบข้อความอัตโนมัติด้วย `!autodel off` ก่อน แล้วค่อยเพิ่มคำ")
        return

    word = word.strip()
    if not word:
        await ctx.reply("❌ ไม่สามารถเพิ่มคำว่างได้")
        return

    key = word.lower()
    if key in AUTO_DELETE_KEYWORDS:
        await ctx.reply(f"ℹ️ คำ `{word}` มีอยู่ในรายการแล้ว")
        return

    AUTO_DELETE_KEYWORDS.add(key)
    await ctx.reply(f"✅ เพิ่มคำสำหรับลบอัตโนมัติ: `{word}`")


@bot.hybrid_command(name="autodel_word_remove", description="ลบคำออกจากรายการกรองลบข้อความอัตโนมัติ (แอดมิน)")
@admin_only()
async def autodel_word_remove(ctx: commands.Context, *, word: str):
    """ลบคำออกจากรายการตัวกรองลบข้อความอัตโนมัติ
    ต้องปิดระบบลบข้อความอัตโนมัติก่อน (!autodel off)
    """
    if AUTO_DELETE_ENABLED:
        await ctx.reply("❌ กรุณาปิดระบบลบข้อความอัตโนมัติด้วย `!autodel off` ก่อน แล้วค่อยลบคำ")
        return

    key = word.strip().lower()
    if not key or key not in AUTO_DELETE_KEYWORDS:
        await ctx.reply("❌ ไม่พบคำนี้ในรายการตัวกรอง")
        return

    AUTO_DELETE_KEYWORDS.remove(key)
    await ctx.reply(f"✅ ลบคำ `{word}` ออกจากรายการตัวกรองแล้ว")


# ---------------- คำสั่งตั้งเวลาในการลบข้อความอัตโนมัติ ----------------

@bot.hybrid_command(name="autodel_delay", description="ตั้งเวลา (วินาที) ที่จะลบข้อความอัตโนมัติ (แอดมิน)")
@admin_only()
async def autodel_delay(ctx: commands.Context, seconds: int):
    """ตั้งค่าเวลาในการลบข้อความอัตโนมัติ (หน่วย: วินาที)
    ต้องปิดระบบลบข้อความอัตโนมัติก่อน (!autodel off)
    """
    global AUTO_DELETE_DELAY_SECONDS

    if AUTO_DELETE_ENABLED:
        await ctx.reply("❌ กรุณาปิดระบบลบข้อความอัตโนมัติด้วย `!autodel off` ก่อน แล้วค่อยตั้งเวลา")
        return

    if seconds < 1 or seconds > 3600:
        await ctx.reply("❌ กรุณาใส่เวลาระหว่าง 1 - 3600 วินาที")
        return

    AUTO_DELETE_DELAY_SECONDS = seconds
    await ctx.reply(f"✅ ตั้งเวลาให้ระบบลบข้อความอัตโนมัติหลังส่ง {seconds} วินาทีแล้ว")


# ---------------- คำสั่งเพิ่มแอดมินของบอทด้วย ID ----------------

@bot.hybrid_command(name="admin_add_id", description="เพิ่มผู้ใช้เป็นแอดมินของบอทด้วย ID (แอดมิน)")
@admin_only()
async def admin_add_id(ctx: commands.Context, user_id: int):
    """เพิ่มผู้ใช้เป็นแอดมินของบอทด้วย user_id"""
    if user_id in ADMIN_IDS or user_id in OWNER_IDS:
        await ctx.reply(f"ℹ️ ผู้ใช้ ID `{user_id}` เป็นแอดมินของบอทอยู่แล้ว")
        return

    ADMIN_IDS.add(user_id)

    # พยายามหา member เพื่อ mention ถ้าอยู่ในกิลด์
    member_mention = f"<@{user_id}>"
    if isinstance(ctx.guild, discord.Guild):
        m = ctx.guild.get_member(user_id)
        if m is not None:
            member_mention = m.mention

    await ctx.reply(f"✅ เพิ่ม {member_mention} (ID: `{user_id}`) เป็นแอดมินของบอทเรียบร้อยแล้ว")


@admin_add_id.error
async def admin_add_id_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.CheckFailure):
        await ctx.reply("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้ (เฉพาะแอดมินของบอท)")


# ---------------- Event on_message (ถามชื่อไฟล์ + ลบข้อความ) ----------------

@bot.event
async def on_message(message: discord.Message):
    # สร้าง task สำหรับลบข้อความอัตโนมัติ (เฉพาะในกลุ่ม)
    if not isinstance(message.channel, discord.DMChannel):
        # ลบเฉพาะข้อความในกลุ่มทุกเซิร์ฟเวอร์ (ตาม TARGET_CHANNEL_IDS และ KEYWORDS)
        bot.loop.create_task(schedule_auto_delete(message))

    # ให้ commands ของบอทยังทำงานตามปกติ (สำคัญมากสำหรับ hybrid / prefix)
    await bot.process_commands(message)

    # ข้ามถ้าข้อความมาจากบอทเอง
    if message.author.bot:
        return

    uid = message.author.id

    # ถ้ามีรอให้ user คนนี้ตอบชื่อไฟล์อยู่ และข้อความนี้ไม่ใช่คำสั่งใหม่
    if uid in pending_name and not message.content.startswith("!"):
        url = pending_name.pop(uid)
        raw = message.content.strip()
        custom_name = None if raw.lower() == "no" else raw

        # เลือกว่าจะส่งไฟล์ใน DM หรือในห้องเดิม
        if isinstance(message.channel, discord.DMChannel):
            target = message.channel
        else:
            try:
                target = await message.author.create_dm()
                await message.reply("กำลังโหลดครับ เดี๋ยวผมจะส่งไฟล์ให้ทาง DM 👍")
            except Exception:
                target = message.channel
                await message.reply("ส่ง DM ไม่ได้ จะส่งในห้องนี้แทนครับ")

        notice = await target.send("⏳ กำลังโหลด...")

        mp3 = None
        try:
            mp3 = await download_mp3(url, custom_name)
            if os.path.getsize(mp3) > 24 * 1024 * 1024:
                await notice.edit(content="⚠️ ไฟล์ใหญ่เกิน ส่งไม่ได้")
            else:
                await notice.edit(content="✅ เสร็จแล้ว ส่งไฟล์ให้แล้วครับ")
                await target.send(file=discord.File(mp3, filename=os.path.basename(mp3)))
        except Exception as e:
            await notice.edit(content=f"❌ Error: {e}")
        finally:
            if mp3:
                temp = os.path.dirname(mp3)
                try:
                    for f in os.listdir(temp):
                        os.remove(os.path.join(temp, f))
                    os.rmdir(temp)
                except Exception:
                    pass


# ---------------- on_ready ----------------

@bot.event
async def on_ready():
    # sync slash commands ให้ขึ้นในเมนู /
    try:
        synced = await bot.tree.sync()
        print(f"ซิงค์ slash commands แล้ว {len(synced)} คำสั่ง")
    except Exception as e:
        print(f"ซิงค์ slash commands ไม่สำเร็จ: {e}")

    print(f"ล็อกอินเป็น {bot.user}")


if __name__ == "__main__":
    bot.run(TOKEN)
