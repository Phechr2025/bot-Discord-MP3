# -*- coding: utf-8 -*-
"""ส่วนของการ์ด + ปุ่ม + Modal สำหรับกรอกแบบฟอร์มแปลงเป็น MP3"""

from typing import Callable, Awaitable, Optional

import discord

FormCallback = Callable[[discord.Interaction, str, str, str], Awaitable[None]]


def build_form_embed(title: str, description: str, image_url: Optional[str] = None) -> discord.Embed:
    """สร้าง Embed สำหรับการ์ดแบบฟอร์ม"""
    embed = discord.Embed(title=title or "mp3", description=description or "ดาวน์โหลด mp3")
    if image_url:
        embed.set_image(url=image_url)
    return embed


class YTMP3Modal(discord.ui.Modal):
    def __init__(self, on_submit: FormCallback, mode: str):
        # title ต้องไม่ยาวเกิน 45 ตัวอักษร
        super().__init__(title="โหลด MP3", timeout=None)
        self._on_submit_cb = on_submit
        self._mode = mode

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
            self._mode,
        )


class YTMP3View(discord.ui.View):
    def __init__(
        self,
        on_submit: FormCallback,
        on_check_queue: Optional[QueueStatusCallback] = None,
    ):
        super().__init__(timeout=None)
        self._on_submit_cb = on_submit
        self._on_check_queue = on_check_queue

    @discord.ui.button(
        label="โหลดแบบ F1 (ปกติ)",
        style=discord.ButtonStyle.primary,
        emoji="1️⃣",
    )
    async def convert_button_f1(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        """ปุ่มโหลดแบบ F1 ใช้วิธีปกติ"""
        modal = YTMP3Modal(self._on_submit_cb, mode="f1")
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="โหลดแบบ F2 (ใช้ cookies)",
        style=discord.ButtonStyle.primary,
        emoji="2️⃣",
    )
    async def convert_button_f2(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        """ปุ่มโหลดแบบ F2 ใช้ cookies.txt เพื่อช่วยโหลดกรณีล็อกอายุ/บอท"""
        modal = YTMP3Modal(self._on_submit_cb, mode="f2")
        await interaction.response.send_modal(modal)

    @discord.ui.button(
        label="เช็คคิวตอนนี้",
        style=discord.ButtonStyle.secondary,
        emoji="📥",
    )
    async def queue_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        """ปุ่มสำหรับเช็คสถานะคิวดาวน์โหลดปัจจุบัน"""
        if self._on_check_queue is None:
            await interaction.response.send_message("ℹ️ ระบบคิวไม่พร้อมใช้งาน", ephemeral=True)
            return
        text = await self._on_check_queue(interaction)
        await interaction.response.send_message(text, ephemeral=True)
