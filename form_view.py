# -*- coding: utf-8 -*-
"""ส่วนของการ์ด + ปุ่ม + Modal สำหรับกรอกแบบฟอร์มแปลงเป็น MP3"""

from typing import Callable, Awaitable, Optional

import discord

FormCallback = Callable[[discord.Interaction, str, str], Awaitable[None]]
QueueStatusCallback = Callable[[], str]


def build_form_embed(title: str, description: str, image_url: Optional[str] = None) -> discord.Embed:
    """สร้าง Embed สำหรับการ์ดแบบฟอร์ม"""
    embed = discord.Embed(title=title or "mp3", description=description or "ดาวน์โหลด mp3")
    if image_url:
        embed.set_image(url=image_url)
    return embed


class YTMP3Modal(discord.ui.Modal):
    def __init__(self, on_submit: FormCallback):
        # title ต้องไม่ยาวเกิน 45 ตัวอักษร
        super().__init__(title="โหลด MP3", timeout=None)
        self._on_submit_cb = on_submit

        # ช่องกรอก URL (label สั้นแน่นอน < 45 ตัว)
        self.url_input: discord.ui.TextInput = discord.ui.TextInput(
            label="URL YouTube",
            placeholder="เช่น https://youtu.be/xxxxxxxxxxx",
            style=discord.TextStyle.short,
            required=True,
            max_length=400,
        )

        # ช่องกรอกชื่อไฟล์ (label สั้นแน่นอน < 45 ตัว)
        self.file_name_input: discord.ui.TextInput = discord.ui.TextInput(
            label="ชื่อไฟล์",
            placeholder="ใส่ชื่อไฟล์ หรือพิมพ์ No เพื่อใช้ชื่อเดิม",
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
    def __init__(self, on_submit: FormCallback, get_queue_text: Optional[QueueStatusCallback] = None):
        super().__init__(timeout=None)
        self._on_submit_cb = on_submit
        self._get_queue_text = get_queue_text

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
        """เวลากดปุ่ม จะเปิด Modal ให้กรอก URL + ชื่อไฟล์"""
        modal = YTMP3Modal(self._on_submit_cb)
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="เช็คคิว",
        style=discord.ButtonStyle.secondary,
        emoji="📊",
    )
    async def queue_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        """ปุ่มเช็คสถานะคิวดาวน์โหลด"""
        if self._get_queue_text is None:
            text = "ไม่มีข้อมูลคิวในตอนนี้"
        else:
            text = self._get_queue_text()
        await interaction.response.send_message(text, ephemeral=True)
