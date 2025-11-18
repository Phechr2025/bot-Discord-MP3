
# form_view.py — ฟอร์ม + ปุ่มแปลงเป็น MP3

import discord

class YTMP3Modal(discord.ui.Modal, title="แปลงเป็น MP3"):
    def __init__(self):
        super().__init__()
        self.url = discord.ui.TextInput(
            label="ลิงก์ YouTube",
            placeholder="ใส่ URL เช่น https://youtu.be/xxxx",
            required=True
        )
        self.filename = discord.ui.TextInput(
            label="ชื่อไฟล์",
            placeholder="ใส่ชื่อไฟล์ หรือ No เพื่อใช้ชื่อจาก YouTube",
            required=True,
            default="No"
        )
        self.add_item(self.url)
        self.add_item(self.filename)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            f"URL: {self.url.value}\nชื่อไฟล์: {self.filename.value}",
            ephemeral=True
        )


class YTMP3View(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="แปลงเป็น MP3", style=discord.ButtonStyle.primary, emoji="🎵")
    async def convert(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(YTMP3Modal())
