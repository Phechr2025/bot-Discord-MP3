
# bot.py — บอทหลัก

import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import tempfile, os, asyncio, uuid

from config import *
from form_view import YTMP3View

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ================== ฟังก์ชันโหลด MP3 ==================

async def download_mp3(url: str, custom_name: str | None = None):
    temp_dir = tempfile.mkdtemp(prefix="ytmp3_")

    def sanitize(name):
        bad=['/','\\',':','*','?','\"','<','>','|']
        for b in bad: name=name.replace(b,'_')
        return name.strip() or str(uuid.uuid4())

    if custom_name and custom_name.lower()!="no":
        outtmpl=os.path.join(temp_dir, sanitize(custom_name)+".%(ext)s")
    else:
        outtmpl=os.path.join(temp_dir, "%(title)s.%(ext)s")

    opts={
        "format":"bestaudio/best",
        "outtmpl":outtmpl,
        "postprocessors":[{"key":"FFmpegExtractAudio","preferredcodec":"mp3","preferredquality":"192"}],
        "quiet":True
    }

    loop=asyncio.get_event_loop()
    def _run():
        with yt_dlp.YoutubeDL(opts) as y: y.download([url])
    await loop.run_in_executor(None,_run)

    for f in os.listdir(temp_dir):
        if f.endswith(".mp3"):
            return os.path.join(temp_dir,f)
    raise FileNotFoundError("ไม่พบ mp3")


# ================== Slash Command ฟอร์ม ==================

@bot.tree.command(name="ytmp3_form", description="เปิดแบบฟอร์มแปลง YouTube เป็น MP3")
async def ytmp3_form(interaction: discord.Interaction):
    await interaction.response.send_message("📄 แบบฟอร์ม:", view=YTMP3View())


# ================== Slash Command ytmp3 (พิมพ์ลิงก์ตรง) ==================

@bot.hybrid_command(name="ytmp3", description="แปลงลิงก์ YouTube เป็น MP3")
async def ytmp3(ctx: commands.Context, url: str):
    await ctx.reply("ต้องการตั้งชื่อไฟล์ว่าอะไร? พิมพ์ No เพื่อใช้ชื่อเดิม")

    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    msg = await bot.wait_for("message", check=check)

    custom = msg.content.strip()
    if custom.lower()=="no": custom=None

    notice = await ctx.reply("⏳ กำลังโหลด...")

    try:
        mp3 = await download_mp3(url, custom)
        await notice.edit(content="ส่งไฟล์แล้ว")
        await ctx.author.send(file=discord.File(mp3))
    except Exception as e:
        await notice.edit(content=f"❌ Error: {e}")


# ================== READY ==================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


bot.run(TOKEN)
