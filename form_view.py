# -*- coding: utf-8 -*-
"""ส่วนของการ์ด + ปุ่ม + Modal สำหรับกรอกแบบฟอร์มแปลงเป็น MP3"""

from typing import Callable, Awaitable, Optional

import discord

FormCallback = Callable[[discord.Interaction, str, str], Awaitable[None]]


def build_form_embed(title: str, description: str, image_url: Optional[str] = None) -> discord.Embed:
    """สร้าง Embed สำหรับการ์ดแบบฟอร์ม"""
    embed = discord.Embed(title=title or "mp3", description=description or "ดาวน์โหลด mp3")
    if image_url:
        embed.set_image(url=image_url)
    return embed


class YTMP3Modal(discord.ui.Modal):
    def __init__(self, on_submit: FormCallback):
        super().__init__(title="แบบฟอร์มแปลงเป็น MP3", timeout=None)
        self._on_submit_cb = on_submit

        self.url_input: discord.ui.TextInput = discord.ui.TextInput(
            label="URL วิดีโอ YouTube (วิดีโอเดี่ยว)",
            placeholder="เช่น https://youtu.be/xxxxxxxxxxx",
            style=discord.TextStyle.short,
            required=True,
            max_length=400,
        )
        self.file_name_input: discord.ui.TextInput = discord.ui.TextInput(
            label="ชื่อไฟล์ที่จะตั้ง (พิมพ์ No เพื่อใช้ชื่อต้นฉบับ)",
            placeholder="เช่น เพลงเพราะๆ หรือพิมพ์ No",
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
        )

        self.add_item(self.url_input)
        self.add_item(self.file_name_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit_cb(
            interaction,
            str(self.url_input.value),
            str(self.file_name_input.value),
        )


class YTMP3View(discord.ui.View):
    def __init__(self, on_submit: FormCallback):
        super().__init__(timeout=None)
        self._on_submit_cb = on_submit

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
        modal = YTMP3Modal(self._on_submit_cb)
        await interaction.response.send_modal(modal)
