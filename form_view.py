import os
import asyncio
from typing import Optional

import discord
import yt_dlp


async def _download_mp3_modal(url: str, custom_name: Optional[str] = None) -> str:
    import tempfile
    import uuid

    temp_dir = tempfile.mkdtemp(prefix="ytmp3_form_")

    def sanitize(name: str) -> str:
        bad = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        for b in bad:
            name = name.replace(b, '_')
        return name.strip() or str(uuid.uuid4())

    if custom_name:
        outtmpl = os.path.join(temp_dir, sanitize(custom_name) + ".%(ext)s")
    else:
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


class YTMP3Modal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="แปลง YouTube เป็น MP3")

        self.url = discord.ui.TextInput(
            label="ลิงก์ YouTube",
            placeholder="https://youtu.be/xxxxxxxxxxx",
            required=True,
            max_length=200,
        )
        self.filename = discord.ui.TextInput(
            label="ชื่อไฟล์ (พิมพ์ No เพื่อใช้ชื่อต้นฉบับจาก YouTube)",
            default="No",
            required=True,
            max_length=100,
        )

        self.add_item(self.url)
        self.add_item(self.filename)

    async def on_submit(self, interaction: discord.Interaction):
        url = str(self.url.value).strip()
        name_raw = str(self.filename.value).strip()
        custom_name = None if name_raw.lower() == "no" else name_raw

        user = interaction.user

        await interaction.response.send_message(
            "⏳ กำลังโหลดและแปลงเป็น MP3 เดี๋ยวจะส่งให้ทาง DM นะครับ",
            ephemeral=True,
        )

        dm = user.dm_channel or await user.create_dm()
        notice = await dm.send("⏳ กำลังโหลดและแปลงเป็นไฟล์ mp3...")

        mp3_path: Optional[str] = None
        try:
            mp3_path = await _download_mp3_modal(url, custom_name)
            size = os.path.getsize(mp3_path)
            if size > 24 * 1024 * 1024:
                await notice.edit(content="⚠️ ไฟล์ใหญ่เกินไป ส่งผ่าน Discord ไม่ได้ครับ")
            else:
                await notice.edit(content="✅ โหลดเสร็จแล้ว ส่งไฟล์ให้แล้วครับ")
                await dm.send(
                    file=discord.File(mp3_path, filename=os.path.basename(mp3_path))
                )
        except Exception as e:
            try:
                await notice.edit(content=f"❌ เกิดข้อผิดพลาด: {e}")
            except Exception:
                pass
        finally:
            if mp3_path:
                temp_dir = os.path.dirname(mp3_path)
                try:
                    for f in os.listdir(temp_dir):
                        os.remove(os.path.join(temp_dir, f))
                    os.rmdir(temp_dir)
                except Exception:
                    pass


class YTMP3View(discord.ui.View):
    def __init__(self, *, timeout: Optional[float] = None):
        super().__init__(timeout=timeout)

    @discord.ui.button(
        label="แปลงเป็น MP3",
        style=discord.ButtonStyle.primary,
        emoji="🎵",
    )
    async def convert_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        modal = YTMP3Modal()
        await interaction.response.send_modal(modal)


def build_ytmp3_form_embed_view(
    title: str,
    description: str,
    image_url: str,
):
    embed = discord.Embed(
        title=title,
        description=description,
        color=0xFF0000,
    )
    embed.set_image(url=image_url)
    embed.set_footer(text="กดปุ่มด้านล่างเพื่อแปลง YouTube เป็น MP3")

    view = YTMP3View()
    return embed, view
