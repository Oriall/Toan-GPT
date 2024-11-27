import os
import asyncio
import discord
from discord.ext import commands
from discord.ui import Button, View
from src.log import logger
from pymongo import MongoClient
from pymongo.server_api import ServerApi
import random
import os
from datetime import datetime, timedelta
import yt_dlp as youtube_dl  # Use yt-dlp instead of youtube_dl
from g4f.client import Client
from g4f.Provider import (RetryProvider, FreeGpt, ChatgptNext, AItianhuSpace,
                        You, OpenaiChat, FreeChatgpt, Liaobots,
                        Gemini, Bing)

from src.aclient import discordClient
from discord import app_commands
from src import log, art, personas

FFMPEG_OPTIONS = {
    'options': '-vn'
}
YDL_OPTIONS = {
    'format': 'bestaudio',
    'noplaylist': True
}
longest_record = {
    "name": None,
    "total_time": 0
}
counting_task = None  # Task dùng để đếm thời gian
start_time = None     # Thời gian bắt đầu đếm
voice_activity = {}
# recordings = {}
uri=os.getenv("MONGO_URI")
monitoring_tasks = {}
image_folder = "./img"
images = [os.path.join(image_folder, img) for img in os.listdir(image_folder) if img.endswith(('.png', '.jpg', '.jpeg'))]
client = MongoClient(uri, server_api=ServerApi('1'))
# Define the RandomImageView class
class RandomImageView(View):
    def __init__(self):
        super().__init__()
        self.current_image = None
        self.update_image()

    def update_image(self):
        # Select a random image
        self.current_image = random.choice(images)

    async def update_embed(self, interaction):
        # Create a new embed and add the image
        embed = discord.Embed(
            title="Album A3K56 :star:",
            color=discord.Color.green()
        )
        # Attach the image to the embed
        file = discord.File(self.current_image, filename="random_image.png")
        embed.set_image(url="attachment://random_image.png")

        # Edit the message with the new embed and image
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)


def run_discord_bot():
    @discordClient.event
    async def on_ready():
        await discordClient.send_start_prompt()
        await discordClient.tree.sync()
        loop = asyncio.get_event_loop()
        loop.create_task(discordClient.process_messages())
        logger.info(f'{discordClient.user} is now running!')

    @discordClient.event
    async def on_voice_state_update(member, before, after):
        voice_client = member.guild.voice_client
        # Kiểm tra xem thành viên có role "BOT" không
        bot_role = discord.utils.get(member.guild.roles, name="BOT")
        if bot_role in member.roles:
            return  # Bỏ qua thành viên có role "BOT"

        if voice_client and after.channel == voice_client.channel:
            # Nếu thành viên mới tham gia kênh thoại và chưa có trong danh sách, thêm vào voice_activity và bắt đầu kiểm tra camera
            if member.id not in voice_activity:
                voice_activity[member.id] = {
                    "name": member.display_name,
                    "start_time": datetime.now(),
                    "total_time": 0
                }
                monitoring_tasks[member.id] = discordClient.loop.create_task(check_camera(member))

            # Nếu thành viên bật camera, hủy nhiệm vụ kiểm tra camera
            if after.self_video and member.id in monitoring_tasks:
                monitoring_tasks[member.id].cancel()
                del monitoring_tasks[member.id]
            # Nếu thành viên tắt camera, bắt đầu lại kiểm tra camera sau 1 phút
            elif not after.self_video and member.id not in monitoring_tasks:
                monitoring_tasks[member.id] = discordClient.loop.create_task(check_camera(member))

        # Nếu thành viên rời khỏi kênh thoại, hủy nhiệm vụ kiểm tra camera và lưu thời gian hoạt động
        elif before.channel == voice_client.channel:
            if member.id in voice_activity:
                total_time = (datetime.now() - voice_activity[member.id]["start_time"]).total_seconds()
                voice_activity[member.id]["total_time"] += total_time
                await save_user_activity(member.id, voice_activity[member.id]["name"], voice_activity[member.id]["total_time"])
                hours, remainder = divmod(voice_activity[member.id]["total_time"], 3600)
                minutes, seconds = divmod(remainder, 60)

                # Gửi thông báo về thời gian học
                channel = discord.utils.get(member.guild.text_channels, name='thông-báo-bot')
                if channel:
                    await channel.send(f"**{member.display_name}** đã học trong vòng {int(hours)} giờ {int(minutes)} phút {int(seconds)} giây trước khi rời kênh thoại.")


                if voice_activity[member.id]["total_time"] > longest_record["total_time"]:
                    longest_record["name"] = member.display_name
                    longest_record["total_time"] = voice_activity[member.id]["total_time"]
                del voice_activity[member.id]

            if member.id in monitoring_tasks:
                monitoring_tasks[member.id].cancel()
                del monitoring_tasks[member.id]

    async def save_user_activity(member_id, member_name, session_time):
        """Lưu thông tin hoạt động của người dùng."""
        db = client['voice_activity_db']
        collection = db['user_activities']

        existing_record = collection.find_one({"user_id": member_id})
        if existing_record:
            total_time = existing_record["total_time"] + session_time
            day_time = existing_record["day_time"] + session_time
            week_time = existing_record["week_time"] + session_time
            month_time = existing_record["month_time"] + session_time
        else:
            total_time = session_time
            day_time = session_time
            week_time = session_time
            month_time = session_time

        data = {
            "user_id": member_id,
            "name": member_name,
            "total_time": total_time,
            "day_time": day_time,
            "week_time": week_time,
            "month_time": month_time,
            "last_updated": datetime.now()
        }
        collection.update_one({"user_id": member_id}, {"$set": data}, upsert=True)

    async def check_camera(member):
        try:
            # Đợi trong 1 phút
            await asyncio.sleep(60)

            # Kiểm tra nếu người dùng không bật camera sau 1 phút và vẫn ở trong kênh
            voice_state = member.guild.voice_client.channel
            if not member.voice.self_video and member.voice and member.voice.channel == voice_state and member.id != discordClient.user.id:
                # Kiểm tra lại role "BOT" trước khi kick
                bot_role = discord.utils.get(member.guild.roles, name="BOT")
                if bot_role not in member.roles:
                    # Tìm kênh 'thông-báo-bot' để gửi thông báo
                    channel = discord.utils.get(member.guild.text_channels, name='thông-báo-bot')
                    if channel:
                        await channel.send(f"**{member.display_name}** đã bị kick khỏi phòng thoại vì không bật camera sau 1 phút.")

                    # Kick người dùng khỏi phòng
                    await member.move_to(None)  # Kick người dùng khỏi phòng thoại
                    await member.send("Bạn đã bị kick khỏi phòng thoại vì không bật camera sau 1 phút.")
        except asyncio.CancelledError:
            # Bỏ qua nếu nhiệm vụ bị hủy (do người dùng đã bật camera)
            pass


    @discordClient.tree.command(name="chat", description="Chat với Chat BotGPT")
    async def chat(interaction: discord.Interaction, *, message: str):
        if discordClient.is_replying_all == "True":
            await interaction.response.defer(ephemeral=False)
            await interaction.followup.send(
                "> **WARN: You already on replyAll mode. If you want to use the Slash Command, switch to normal mode by using `/replyall` again**")
            logger.warning("\x1b[31mYou already on replyAll mode, can't use slash command!\x1b[0m")
            return
        if interaction.user == discordClient.user:
            return
        username = str(interaction.user)
        discordClient.current_channel = interaction.channel
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /chat [{message}] in ({discordClient.current_channel})")

        await discordClient.enqueue_message(interaction, message)


    @discordClient.tree.command(name="private", description="Hiện thị tin nhắn cá nhân")
    async def private(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if not discordClient.isPrivate:
            discordClient.isPrivate = not discordClient.isPrivate
            logger.warning("\x1b[31mSwitch to private mode\x1b[0m")
            await interaction.followup.send(
                "> **INFO: Next, the response will be sent via private reply. If you want to switch back to public mode, use `/public`**")
        else:
            logger.info("You already on private mode!")
            await interaction.followup.send(
                "> **WARN: You already on private mode. If you want to switch to public mode, use `/public`**")


    @discordClient.tree.command(name="public", description="Hiện thị tin nhắn cộng đồng")
    async def public(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        if discordClient.isPrivate:
            discordClient.isPrivate = not discordClient.isPrivate
            await interaction.followup.send(
                "> **INFO: Next, the response will be sent to the channel directly. If you want to switch back to private mode, use `/private`**")
            logger.warning("\x1b[31mSwitch to public mode\x1b[0m")
        else:
            await interaction.followup.send(
                "> **WARN: You already on public mode. If you want to switch to private mode, use `/private`**")
            logger.info("You already on public mode!")

    @discordClient.tree.command(name="top", description="Hiển thị bảng xếp hạng thời gian hoạt động của các thành viên.")
    @app_commands.describe(duration="Khoảng thời gian xếp hạng (Day, Week, Month)")
    @app_commands.choices(
        duration=[
            app_commands.Choice(name="Day", value="day_time"),
            app_commands.Choice(name="Week", value="week_time"),
            app_commands.Choice(name="Month", value="month_time")
        ]
    )
    async def show_top(interaction: discord.Interaction, duration: app_commands.Choice[str] = None):
        db = client['voice_activity_db']
        collection = db['user_activities']

        # Nếu không nhập tham số, sử dụng 'total_time'
        field = duration.value if duration else "total_time"
        title = duration.name if duration else "Total"

        # Lấy dữ liệu từ MongoDB và sắp xếp
        records = list(collection.find().sort(field, -1))

        if not records:
            await interaction.response.send_message(f"Không có dữ liệu cho bảng xếp hạng {title}.")
            return

        # Tạo bảng xếp hạng
        embed = discord.Embed(
            title=f"🏆 Bảng Xếp Hạng Thời Gian Hoạt Động ({title})",
            description="```plaintext\n" + "Rank    User              Time\n" + "---------------------------------" + "\n",
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url="https://i.pinimg.com/originals/ea/fb/38/eafb38b7973b0f65459532cc17e16fbe.gif")

        medals = ["🥇", "🥈", "🥉"]
        for i, record in enumerate(records[:10], start=1):  # Hiển thị top 10
            hours, remainder = divmod(record[field], 3600)
            minutes, seconds = divmod(remainder, 60)
            time_string = f"{int(hours)}h {int(minutes)}m {int(seconds)}s"
            medal = medals[i - 1] if i <= 3 else ""

            # Định dạng tên và thời gian
            user_name = record['name'][:12].ljust(12)  # Cắt ngắn hoặc làm dài tên
            line = f"{i:<3}{medal:<3} {user_name:<15} {time_string}"
            embed.description += f"{line}\n"

        embed.description += "```"
        await interaction.response.send_message(embed=embed)

    # Lệnh `/reset` để đặt lại thời gian
    @discordClient.tree.command(name="reset_top", description="Đặt lại thời gian hoạt động của các thành viên.")
    @app_commands.describe(duration="Khoảng thời gian cần đặt lại (Day, Week, Month)")
    @app_commands.choices(
        duration=[
            app_commands.Choice(name="Day", value="day_time"),
            app_commands.Choice(name="Week", value="week_time"),
            app_commands.Choice(name="Month", value="month_time")
        ]
    )
    async def reset_time(interaction: discord.Interaction, duration: app_commands.Choice[str]):
        db = client['voice_activity_db']
        collection = db['user_activities']
        field_to_reset = duration.value
        collection.update_many({}, {"$set": {field_to_reset: 0}})
        await interaction.response.send_message(f"Đã đặt lại dữ liệu {duration.name} thành công!")

    @discordClient.tree.command(name="profile", description="Hiển thị thông tin profile cá nhân hoặc của người dùng khác.")
    @app_commands.describe(member="Người dùng muốn xem profile (để trống để xem của chính bạn).")
    async def profile(interaction: discord.Interaction, member: discord.Member = None):
        db = client['voice_activity_db']
        collection = db['user_activities']

        # Nếu không chọn member, lấy profile của chính người dùng
        target_user = member or interaction.user
        user_data = collection.find_one({"user_id": target_user.id})

        if not user_data:
            await interaction.response.send_message(
                f"Không tìm thấy dữ liệu của {'bạn' if target_user == interaction.user else target_user.display_name}.",
                ephemeral=True
            )
            return

        # Lấy thứ hạng từ tổng thời gian
        all_users = list(collection.find().sort("total_time", -1))
        rank_position = next((index + 1 for index, user in enumerate(all_users) if user["user_id"] == target_user.id), None)

        # Tính toán XP và Rank
        total_xp = int(user_data["total_time"] // 60)  # 1 phút = 1 XP
        rank = determine_rank(total_xp)

        # Hình ảnh rank theo cấp độ
        rank_images = {
            "sắt": "https://i.pinimg.com/originals/5b/d9/89/5bd98999e33567902b7e95b33c2db20e.gif",
            "đồng": "https://i.pinimg.com/originals/e9/c8/d7/e9c8d789f753088fe97057a3bdadfa75.gif",
            "vàng": "https://tenor.com/vi/view/league-of-legends-rankup-gold-gif-21928002",
            "bạch kim": "https://tenor.com/vi/view/league-of-legends-rankup-platinum-gif-21927987",
            "kim cương": "https://i.pinimg.com/originals/9c/d0/b4/9cd0b467e35e79fdb14e5cfc89c56201.gif",
            "tinh anh": "https://i.pinimg.com/originals/24/79/65/247965dc76dac892df2d4e6b9d7fcc33.gif",
            "cao thủ": "https://i.pinimg.com/originals/43/25/1a/43251a05025f722d110ad73852f7ac66.gif",
            "đại cao thủ": "https://tenor.com/vi/view/challenger-rankup-lol-gif-10205023597477411344"
        }
        rank_image = rank_images.get(rank.split()[0].lower(), None)

        # Tính toán thanh XP
        xp_ranges = [
            (0, 500), (501, 1000), (1001, 1500), (1501, 2000), (2001, 3000), (3001, 4000),
            (4001, 5000), (5001, 6000), (6001, 7000), (7001, 8000), (8001, 9000),
            (9001, 10000), (10001, 11500), (11501, 13000), (13001, 14500), (14501, 16000),
            (16001, 17500), (17501, 19000), (19001, 22000), (22001, 25000), (25001, 28000),
            (28001, 31000), (31001, 40000), (40001, float('inf'))
        ]
        for i, (min_xp, max_xp) in enumerate(xp_ranges):
            if min_xp <= total_xp <= max_xp:
                xp_for_next_rank = max_xp
                xp_current_rank = min_xp
                break

        xp_remaining = xp_for_next_rank - total_xp
        progress_percentage = int((total_xp - xp_current_rank) / (xp_for_next_rank - xp_current_rank) * 100)
        progress_bar = "█" * (progress_percentage // 10) + "░" * (10 - progress_percentage // 10)

        # Embed lớn
        embed_color = discord.Color.dark_gray()  # Mặc định màu xám
        footer_text = None
        footer_icon_url = None

        # Đặc biệt cho Top 1, 2, 3
        if rank_position == 1:
            embed_color = discord.Color.from_str("#E85C0D")
            footer_text = "Top 1"
            footer_icon_url = "https://i.pinimg.com/originals/36/8d/0d/368d0d9c9fca6814127972f33137d788.gif"
        elif rank_position == 2:
            embed_color = discord.Color.from_str("#8B5DFF") 
            footer_text = "Top 2"
            footer_icon_url = "https://i.pinimg.com/originals/86/72/b6/8672b63a4da897c9b3040daefc215da2.gif"
        elif rank_position == 3:
            embed_color = discord.Color.from_str("#D4EBF8")
            footer_text = "Top 3"
            footer_icon_url = "https://i.pinimg.com/originals/0a/a1/95/0aa19599cffaf13ae7f9914b1919499b.gif"

        embed = discord.Embed(
            title=f"🎓 Hồ Sơ Của {target_user.display_name}",
            color=embed_color
        )
        embed.add_field(name="🏅 Rank", value=f"**{rank}**", inline=False)
        embed.add_field(name="🕒 Tổng Thời Gian Học", value=f"{user_data['total_time'] // 3600} giờ", inline=True)
        embed.add_field(name="⭐ XP", value=f"{total_xp} XP", inline=True)
        embed.add_field(name="🤖 Tiến Độ Lên Rank", value=f"XP hiện tại: **{total_xp}**\nXP cần cho rank tiếp theo: **{xp_remaining}**\n\n{progress_bar} **{progress_percentage}%**", inline=False)
        embed.set_thumbnail(url=target_user.avatar.url if target_user.avatar else target_user.default_avatar.url)

        if rank_image:
            embed.set_image(url=rank_image)
        if footer_text and footer_icon_url:
            embed.set_footer(text=footer_text, icon_url=footer_icon_url)

        await interaction.response.send_message(embed=embed)







    def determine_rank(xp):
        """Xác định rank dựa trên tổng XP"""
        if xp <= 500:
            return "Sắt 3"
        elif xp <= 1000:
            return "Sắt 2"
        elif xp <= 1500:
            return "Sắt 1"
        elif xp <= 2000:
            return "Đồng 3"
        elif xp <= 3000:
            return "Đồng 2"
        elif xp <= 4000:
            return "Đồng 1"
        elif xp <= 5000:
            return "Vàng 3"
        elif xp <= 6000:
            return "Vàng 2"
        elif xp <= 7000:
            return "Vàng 1"
        elif xp <= 8000:
            return "Bạch Kim 3"
        elif xp <= 9000:
            return "Bạch Kim 2"
        elif xp <= 10000:
            return "Bạch Kim 1"
        elif xp <= 11500:
            return "Kim Cương 3"
        elif xp <= 13000:
            return "Kim Cương 2"
        elif xp <= 14500:
            return "Kim Cương 1"
        elif xp <= 16000:
            return "Tinh Anh 3"
        elif xp <= 17500:
            return "Tinh Anh 2"
        elif xp <= 19000:
            return "Tinh Anh 1"
        elif xp <= 22000:
            return "Cao Thủ 5"
        elif xp <= 25000:
            return "Cao Thủ 4"
        elif xp <= 28000:
            return "Cao Thủ 3"
        elif xp <= 31000:
            return "Cao Thủ 2"
        elif xp <= 40000:
            return "Cao Thủ 1"
        else:
            return "Đại Cao Thủ"

    @discordClient.tree.command(name="rank", description="Hiển thị thông tin chi tiết về các mức rank.")
    async def rank(interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏅 Hệ Thống Rank",
            description="Chi tiết về các mức rank dựa trên thời gian hoạt động (1 phút = 1 XP):",
            color=discord.Color.dark_theme()
        )
        embed.set_thumbnail(url="https://i.pinimg.com/originals/e7/90/f2/e790f26acee065b349c5dabd840638ae.gif")
        
        rank_details = [
            ("Sắt 3", "0 - 500 XP"),
            ("Sắt 2", "501 - 1000 XP"),
            ("Sắt 1", "1001 - 1500 XP"),
            ("Đồng 3", "1501 - 2000 XP"),
            ("Đồng 2", "2001 - 3000 XP"),
            ("Đồng 1", "3001 - 4000 XP"),
            ("Vàng 3", "4001 - 5000 XP"),
            ("Vàng 2", "5001 - 6000 XP"),
            ("Vàng 1", "6001 - 7000 XP"),
            ("Bạch Kim 3", "7001 - 8000 XP"),
            ("Bạch Kim 2", "8001 - 9000 XP"),
            ("Bạch Kim 1", "9001 - 10,000 XP"),
            ("Kim Cương 3", "10,001 - 11,500 XP"),
            ("Kim Cương 2", "11,501 - 13,000 XP"),
            ("Kim Cương 1", "13,001 - 14,500 XP"),
            ("Tinh Anh 3", "14,501 - 16,000 XP"),
            ("Tinh Anh 2", "16,001 - 17,500 XP"),
            ("Tinh Anh 1", "17,501 - 19,000 XP"),
            ("Cao Thủ 5", "19,001 - 22,000 XP"),
            ("Cao Thủ 4", "22,001 - 25,000 XP"),
            ("Cao Thủ 3", "25,001 - 28,000 XP"),
            ("Cao Thủ 2", "28,001 - 31,000 XP"),
            ("Cao Thủ 1", "31,001 - 40,000 XP"),
            ("Đại Cao Thủ", "Trên 40,000 XP"),
        ]

        for rank, range_xp in rank_details:
            embed.add_field(name=f"🎖 {rank}", value=f"**XP**: {range_xp}", inline=False)

        await interaction.response.send_message(embed=embed)

    @discordClient.tree.command(name="version", description="Hiển thị thông tin cập nhật mới nhất của bot.")
    async def version(interaction: discord.Interaction):
        updates = [
            "🆕 **1.0.1** - Thêm lệnh `/top` để hiển thị bảng xếp hạng thời gian học.",
            "🔧 **1.0.2** - Cải thiện hiệu suất khi lưu thời gian học vào database MongoDB.",
            "✨ **1.0.3** - Thêm lệnh `/version` để xem các bản cập nhật mới nhất.",
            "🔥 **1.0.4** - Thêm bot `a3k56` quản lý các kênh trong danh mục riêng.",
            "💡 **1.1.0** - Thêm lệnh `/profile` với hệ thống XP và Rank mới.",
            "🌟 **1.1.1** - Bổ sung lệnh `/reset_top` để reset bảng xếp hạng thời gian học.(Quyền Admin)",
            "⚡ **1.2.0** - Cải tiến giao diện hiển thị thời gian học trong embed của `/top`.",
            "🏅 **1.2.1** - Chi tiết hệ thống **XP & Rank**:",
            "   • **1 phút = 1 XP.**",
            "   • **Cấp bậc:**",
            "      - Sắt: 0-1500 XP (3 cấp).",
            "      - Đồng: 1501-4000 XP (3 cấp).",
            "      - Vàng: 4001-7000 XP (3 cấp).",
            "      - Bạch Kim: 7001-10000 XP (3 cấp).",
            "      - Kim Cương: 10,001-14,500 XP (3 cấp).",
            "      - Tinh Anh: 14,501-19,000 XP (3 cấp).",
            "      - Cao Thủ: 19,001-40,000 XP (5 cấp).",
            "      - Đại Cao Thủ: >40,000 XP."
        ]

        embed = discord.Embed(
            title="📦 Cập Nhật Mới Nhất (Version 1.1)",
            description="Danh sách các bản cập nhật và cải tiến gần đây cho bot:",
            color=discord.Color.green()
        )

        for update in updates:
            embed.add_field(name="•", value=update, inline=False)
        
        # Thêm ảnh GIF
        embed.set_thumbnail(url="https://i.pinimg.com/originals/87/5d/6a/875d6a6b9f4f45578e07f995d51d4973.gif")

        await interaction.response.send_message(embed=embed)

    @discordClient.tree.command(name="gacha", description="Tiêu 15 XP để thử vận may và nhận lá bài ngẫu nhiên!")
    async def gacha(interaction: discord.Interaction):
        db = client['voice_activity_db']
        collection = db['user_activities']

        user_data = collection.find_one({"user_id": interaction.user.id})

        # Kiểm tra nếu người dùng không có đủ XP
        if not user_data or user_data.get("total_time", 0) < 15 * 60:  # 15 phút tương ứng 20 XP
            await interaction.response.send_message(
                "Bạn không có đủ **20 XP** (tương đương 15 phút) để thực hiện gacha.",
                ephemeral=True
            )
            return

        
        collection.update_one(
            {"user_id": interaction.user.id},
            {"$inc": {"total_time": -15 * 60}}  # 20 XP = 20 * 60 giây
        )

        # Tỷ lệ các lá bài (tổng 100%)
        cards = [
            {"xp": -50, "probability": 5, "image": "https://i.ibb.co/hfg8Tcw/question-card.jpg", "name": "C"},  # Hỏi chấm
            {"xp": 0, "probability": 20, "image": "https://i.ibb.co/7Cd1YSh/IMG-20220922-091545.jpg", "name": "C+"},  # Phần lớn
            {"xp": 10, "probability": 25, "image": "https://i.ibb.co/sp4mCgD/IMG-20230324-160210.jpg", "name": "R"},  # Bình thường 1
            {"xp": 20, "probability": 20, "image": "https://i.ibb.co/zb4B8dZ/IMG-2599.jpg", "name": "R+"},  # Bình thường 2
            {"xp": 30, "probability": 12, "image": "https://i.ibb.co/xsrF9kL/IMG-1355.jpg", "name": "SSR"},  # Khá hiếm
            {"xp": 50, "probability": 10, "image": "https://ibb.co/Np8tztz", "name": "SSR+"},  # Hiếm
            {"xp": 100, "probability": 5, "image": "https://i.ibb.co/jGcbFbF/anh-bg.jpg", "name": "UR"},  # Rất hiếm 1
            {"xp": 150, "probability": 1.5, "image": "https://i.ibb.co/QPv9cRS/lp.jpg", "name": "UR+"},  # Rất hiếm 2
            {"xp": 300, "probability": 1, "image": "https://i.ibb.co/42vrHk6/IMG-1037-HEIC-1.jpg", "name": "M+"},  # Sử thi
            {"xp": 500, "probability": 0.4, "image": "https://i.ibb.co/v1J9hqC/df.jpg", "name": "EX"},  # Huyền thoại
            {"xp": 1000, "probability": 0.1, "image": "https://i.ibb.co/PCYtvJf/image.jpg", "name": "LEGEND"}  # 1 lá duy nhất
        ]

        
        roll = random.uniform(0, 100)
        cumulative_probability = 0
        selected_card = None

        for card in cards:
            cumulative_probability += card["probability"]
            if roll <= cumulative_probability:
                selected_card = card
                break

        
        if selected_card:
            collection.update_one(
                {"user_id": interaction.user.id},
                {"$inc": {"total_time": selected_card["xp"] * 60}}  # XP = phút * 60 giây
            )

      
        embed = discord.Embed(
            title="🎲 Kết Quả Gacha!",
            description=f"Bạn đã tiêu **15 XP** và nhận được lá bài:",
            color=discord.Color.orange()
        )
        embed.add_field(name="🎁 Lá bài", value=f"**{selected_card['name']}**", inline=False)
        embed.add_field(name="⭐ XP Nhận Được", value=f"{'+' if selected_card['xp'] >= 0 else ''}{selected_card['xp']} XP", inline=False)
        embed.set_image(url=selected_card["image"])
        embed.set_footer(text="Chúc bạn may mắn lần sau!", icon_url="https://i.pinimg.com/originals/36/8d/0d/368d0d9c9fca6814127972f33137d788.gif")

       
        await interaction.response.send_message(embed=embed)

        
    @discordClient.tree.command(name="rule_gacha", description="Hiển thị luật chơi và tỷ lệ nhận bài trong gacha.")
    async def rule_gacha(interaction: discord.Interaction):
        # Embed chứa luật gacha
        embed = discord.Embed(
            title="🎲 Luật Chơi Gacha 🎲",
            description="Sử dụng **15 XP** mỗi lần để tham gia Gacha và có cơ hội nhận được các lá bài với phần thưởng khác nhau! Đây là các lá bài và tỷ lệ nhận được:",
            color=discord.Color.orange()
        )

        # Danh sách các loại bài
        rules = [
            {"name": "❓ Hỏi chấm", "xp": "-50 XP", "probability": "5%", "image": "https://i.ibb.co/hfg8Tcw/question-card.jpg"},
            {"name": "🟠 Phần lớn", "xp": "+0 XP", "probability": "20%", "image": "https://i.ibb.co/7Cd1YSh/IMG-20220922-091545.jpg"},
            {"name": "🔵 Bình thường 1", "xp": "+10 XP", "probability": "25%", "image": "https://i.ibb.co/sp4mCgD/IMG-20230324-160210.jpg"},
            {"name": "🟢 Bình thường 2", "xp": "+20 XP", "probability": "20%", "image": "https://i.ibb.co/zb4B8dZ/IMG-2599.jpg"},
            {"name": "🟡 Khá hiếm", "xp": "+30 XP", "probability": "12%", "image": "https://i.ibb.co/xsrF9kL/IMG-1355.jpg"},
            {"name": "🔴 Hiếm", "xp": "+50 XP", "probability": "10%", "image": "https://ibb.co/Np8tztz"},
            {"name": "💎 Rất hiếm 1", "xp": "+100 XP", "probability": "5%", "image": "https://i.ibb.co/jGcbFbF/anh-bg.jpg"},
            {"name": "💎 Rất hiếm 2", "xp": "+150 XP", "probability": "1.5%", "image": "https://i.ibb.co/QPv9cRS/lp.jpg"},
            {"name": "🌟 Sử thi", "xp": "+300 XP", "probability": "1%", "image": "https://i.ibb.co/42vrHk6/IMG-1037-HEIC-1.jpg"},
            {"name": "🌌 Huyền thoại", "xp": "+500 XP", "probability": "0.4%", "image": "https://i.ibb.co/v1J9hqC/df.jpg"},
            {"name": "🏆 1 lá duy nhất", "xp": "+1000 XP", "probability": "0.1%", "image": "https://i.ibb.co/PCYtvJf/image.jpg"}
        ]

        # Thêm thông tin từng loại bài vào Embed
        for rule in rules:
            embed.add_field(
                name=f"{rule['name']}",
                value=f"**XP:** {rule['xp']}\n**Tỷ lệ:** {rule['probability']}",
                inline=False
            )

        # Chèn hình ảnh minh họa
        embed.set_thumbnail(url="https://i.ibb.co/v1J9hqC/df.jpg")
        embed.set_footer(
            text="Hãy thử vận may với /gacha hoặc /all_in!",
            icon_url="https://i.pinimg.com/originals/36/8d/0d/368d0d9c9fca6814127972f33137d788.gif"
        )

        # Gửi Embed đến người dùng
        await interaction.response.send_message(embed=embed)

    @discordClient.tree.command(name="all_in", description="Thử vận may bằng cách thực hiện gacha 10 lần liên tiếp!")
    async def all_in(interaction: discord.Interaction):
        db = client['voice_activity_db']
        collection = db['user_activities']

        user_data = collection.find_one({"user_id": interaction.user.id})

        # Kiểm tra nếu người dùng không có đủ XP cho 10 lần gacha
        total_xp_required = 15 * 60 * 10  # 15 phút * 60 giây * 10 lần
        if not user_data or user_data.get("total_time", 0) < total_xp_required:
            await interaction.response.send_message(
                f"Bạn không có đủ **200 XP** (tương đương 150 phút) để thực hiện 10 lần gacha.",
                ephemeral=True
            )
            return

        # Trừ tổng XP cần thiết cho 10 lần gacha
        collection.update_one(
            {"user_id": interaction.user.id},
            {"$inc": {"total_time": -total_xp_required}}
        )

        # Tỷ lệ các lá bài (tổng 100%)
        cards = [
            {"xp": -50, "probability": 5, "image": "https://i.ibb.co/7Cd1YSh/IMG-20220922-091545.jpg", "name": "C"},  # Hỏi chấm
            {"xp": 0, "probability": 20, "image": "https://i.ibb.co/7Cd1YSh/IMG-20220922-091545.jpg", "name": "C+"},  # Phần lớn
            {"xp": 10, "probability": 25, "image": "https://i.ibb.co/sp4mCgD/IMG-20230324-160210.jpg", "name": "R"},  # Bình thường 1
            {"xp": 20, "probability": 20, "image": "https://i.ibb.co/zb4B8dZ/IMG-2599.jpg", "name": "R+"},  # Bình thường 2
            {"xp": 30, "probability": 12, "image": "https://i.ibb.co/xsrF9kL/IMG-1355.jpg", "name": "SSR"},  # Khá hiếm
            {"xp": 50, "probability": 10, "image": "https://ibb.co/Np8tztz", "name": "SSR+"},  # Hiếm
            {"xp": 100, "probability": 5, "image": "https://i.ibb.co/jGcbFbF/anh-bg.jpg", "name": "UR"},  # Rất hiếm 1
            {"xp": 150, "probability": 1.5, "image": "https://i.ibb.co/QPv9cRS/lp.jpg", "name": "UR+"},  # Rất hiếm 2
            {"xp": 300, "probability": 1, "image": "https://i.ibb.co/42vrHk6/IMG-1037-HEIC-1.jpg", "name": "M+"},  # Sử thi
            {"xp": 500, "probability": 0.4, "image": "https://i.ibb.co/v1J9hqC/df.jpg", "name": "EX"},  # Huyền thoại
            {"xp": 1000, "probability": 0.1, "image": "https://i.ibb.co/PCYtvJf/image.jpg", "name": "LEGEND"}  # 1 lá duy nhất
        ]

        # Kết quả 10 lần gacha
        results = []
        total_xp_gained = 0

        for _ in range(10):
            roll = random.uniform(0, 100)
            cumulative_probability = 0
            selected_card = None

            for card in cards:
                cumulative_probability += card["probability"]
                if roll <= cumulative_probability:
                    selected_card = card
                    break

            if selected_card:
                # Cộng XP của từng lần gacha
                collection.update_one(
                    {"user_id": interaction.user.id},
                    {"$inc": {"total_time": selected_card["xp"] * 60}}
                )
                results.append(selected_card)
                total_xp_gained += selected_card["xp"]

        # Tạo Embed kết quả
        embed = discord.Embed(
            title="🎲 Kết Quả All-In!",
            description=f"Bạn đã thực hiện **10 lần gacha** và đây là kết quả:",
            color=discord.Color.orange()
        )
        for i, result in enumerate(results, start=1):
            embed.add_field(
                name=f"Lần {i}: {result['name']}",
                value=f"⭐ XP: {'+' if result['xp'] >= 0 else ''}{result['xp']} XP",
                inline=False
            )
        embed.add_field(
            name="Tổng XP Nhận Được",
            value=f"{'+' if total_xp_gained >= 0 else ''}{total_xp_gained} XP",
            inline=False
        )
        embed.set_footer(text="Chúc bạn may mắn lần sau!", icon_url="https://i.pinimg.com/originals/36/8d/0d/368d0d9c9fca6814127972f33137d788.gif")

        # Gửi kết quả cho người dùng
        await interaction.response.send_message(embed=embed)

    @discordClient.tree.command(name="replyall", description="Toggle replyAll access")
    async def replyall(interaction: discord.Interaction):
        discordClient.replying_all_discord_channel_id = str(interaction.channel_id)
        await interaction.response.defer(ephemeral=False)
        if discordClient.is_replying_all == "True":
            discordClient.is_replying_all = "False"
            await interaction.followup.send(
                "> **INFO: Next, the bot will response to the Slash Command. If you want to switch back to replyAll mode, use `/replyAll` again**")
            logger.warning("\x1b[31mSwitch to normal logger.info mode\x1b[0m")
        elif discordClient.is_replying_all == "False":
            discordClient.is_replying_all = "True"
            await interaction.followup.send(
                "> **INFO: Next, the bot will disable Slash Command and responding to all message in this channel only. If you want to switch back to normal mode, use `/replyAll` again**")
            logger.warning("\x1b[31mSwitch to replyAll mode\x1b[0m")


    @discordClient.tree.command(name="chat-model", description="Chuyển sang con bot khác Gemini, GPT, ...'")
    @app_commands.choices(model=[
        app_commands.Choice(name="gemeni", value="gemeni"),
        app_commands.Choice(name="gpt-4", value="gpt-4"),
        app_commands.Choice(name="gpt-3.5-turbo", value="gpt-3.5-turbo"),
    ])
    async def chat_model(interaction: discord.Interaction, model: app_commands.Choice[str]):
        await interaction.response.defer(ephemeral=True)
        try:
            if model.value == "gemeni":
                discordClient.reset_conversation_history()
                discordClient.chatBot = Client(provider=RetryProvider([Gemini, FreeChatgpt], shuffle=False))
                discordClient.chatModel = model.value
            elif model.value == "gpt-4":
                discordClient.reset_conversation_history()
                discordClient.chatBot = Client(provider=RetryProvider([Liaobots, You, OpenaiChat, Bing], shuffle=False))
                discordClient.chatModel = model.value
            elif model.value == "gpt-3.5-turbo":
                discordClient.reset_conversation_history()
                discordClient.chatBot = Client(provider=RetryProvider([FreeGpt, ChatgptNext, AItianhuSpace], shuffle=False))
                discordClient.chatModel = model.value

            await interaction.followup.send(f"> **INFO: Chat model switched to {model.name}.**")
            logger.info(f"Switched chat model to {model.name}")

        except Exception as e:
            await interaction.followup.send(f'> **Error Switching Model: {e}**')
            logger.error(f"Error switching chat model: {e}")

    @discordClient.tree.command(name="reset", description="Xóa lịch sử trò chuyện")
    async def reset(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        discordClient.conversation_history = []
        await interaction.followup.send("> **INFO: I have forgotten everything.**")
        personas.current_persona = "standard"
        logger.warning(
            f"\x1b[31m{discordClient.chatModel} bot has been successfully reset\x1b[0m")

#----------------------------------join-----------------------------------------------
    @discordClient.tree.command(name="join", description="Tham gia phòng thoại")
    async def join(interaction: discord.Interaction):
        # Kiểm tra người dùng có ở trong voice channel nào không
        if interaction.user.voice is None or interaction.user.voice.channel is None:
            await interaction.response.send_message("Bạn cần tham gia một phòng thoại trước khi dùng lệnh này.", ephemeral=True)
            return

        # Lấy voice channel của người dùng
        voice_channel = interaction.user.voice.channel

        # Kiểm tra bot có đang tham gia voice channel nào không
        if interaction.guild.voice_client is not None:
            if interaction.guild.voice_client.channel == voice_channel:
                await interaction.response.send_message("Bot đã có trong phòng thoại này rồi.", ephemeral=True)
                return
            else:
                await interaction.guild.voice_client.disconnect()

        # Kết nối bot vào voice channel
        await voice_channel.connect()
        await interaction.response.send_message(f"Đã tham gia phòng thoại **{voice_channel}**!")
        

    @discordClient.tree.command(name="record", description="Xem thời gian hoạt động dài nhất từng được ghi lại")
    async def record(interaction: discord.Interaction):
        global longest_record

        # Kiểm tra nếu có ai đã lập kỷ lục
        if longest_record["name"] is None:
            await interaction.response.send_message("Chưa có kỷ lục nào được ghi nhận.")
            return

        # Hiển thị kỷ lục về thời gian hoạt động dài nhất
        hours, remainder = divmod(longest_record["total_time"], 3600)
        minutes, seconds = divmod(remainder, 60)
        embed = discord.Embed(
            title="🏅 Kỷ Lục Hoạt Động Lâu Nhất",
            description=(
                f"Thành viên **{longest_record['name']}** hiện đang giữ kỷ lục hoạt động lâu nhất trong kênh thoại."
            ),
            color=discord.Color.gold()
        )
        embed.add_field(
            name="Thời gian kỷ lục",
            value=f"{int(hours)} giờ {int(minutes)} phút {int(seconds)} giây",
            inline=False
        )
        embed.set_thumbnail(url='https://i.pinimg.com/originals/06/0d/31/060d31d4d6edee071a2aa092a20b4512.gif')  # Hiển thị avatar của thành viên giữ kỷ lục
        embed.set_footer(text="Hãy cố gắng lập kỷ lục mới nhé! 💪🔥")

        # Gửi thông báo với embed
        await interaction.response.send_message(embed=embed)

    @discordClient.tree.command(name="tao_phong", description="Tạo một phòng thoại trong danh mục 'hoạt động chung'")
    @app_commands.describe(ten_phong="Tên của phòng thoại mới")
    async def tao_phong(interaction: discord.Interaction, ten_phong: str):

        category = discord.utils.get(interaction.guild.categories, name="HOẠT ĐỘNG RIÊNG")

        if category is None:
            await interaction.response.send_message("Không tìm thấy danh mục 'hoạt động chung'.", ephemeral=True)
            return

        # Tạo phòng thoại với tên do người dùng nhập
        new_voice_channel = await interaction.guild.create_voice_channel(name=ten_phong, category=category)
        await interaction.response.send_message(f"Đã tạo phòng thoại mới: **{new_voice_channel.name}** trong danh mục 'hoạt động chung'.")

    @discordClient.tree.command(name="start_time", description="Bắt đầu đếm ngược thời gian")
    async def start_time(interaction: discord.Interaction, hours: int = 0, minutes: int = 0, seconds: int = 0):
        # Tính tổng thời gian đếm ngược
        total_seconds = hours * 3600 + minutes * 60 + seconds

        if total_seconds <= 0:
            await interaction.response.send_message("Vui lòng nhập thời gian hợp lệ.", ephemeral=True)
            return

        # Xác nhận đã bắt đầu đếm ngược
        await interaction.response.send_message(f"Bắt đầu đếm ngược: {hours} giờ, {minutes} phút, {seconds} giây. Tập trung nào!! 👏👏")

        # Đếm ngược
        await asyncio.sleep(total_seconds)

        # Lấy tên người ra lệnh
        user_name = interaction.user.display_name

        # Tạo embed thông báo khi đếm ngược hoàn tất
        embed = discord.Embed(
            title="Đã hết thời gian !! 🎉",
            description=f"Hết thời gian rồi @{user_name}!",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Vào Sever!",
            value="[Vào Sever để được nhận hỗ trợ từ Dev!](https://discord.gg/78TnsrJd)",
            inline=False
        )
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/3193/3193311.png")  # Đường dẫn tới hình ảnh của bạn

        # Gửi embed
        await interaction.followup.send(embed=embed)

    @discordClient.tree.command(name='addbot', description="Link mời Bot vào Sever")
    async def _addbot(interaction: discord.Interaction):
        embed = discord.Embed(
        title="Mời Tôi",
        description="Cick vào link để mời tôi vào Sever thôi nào!",
        color=discord.Color.blue()
        )
        embed.add_field(
            name="Mời Bot!",
            value="[Click để sử dụng bot trong sever của bạn!!](https://discord.com/oauth2/authorize?client_id=1228367902135029830&scope=bot)",
            inline=False
        )
        embed.set_thumbnail(url="https://i.imgur.com/CZFt69d.png")  # Replace with a URL to your desired image

        await interaction.response.send_message(embed=embed)
    @discordClient.tree.command(name="album", description="Hiện thị 1 ảnh ngẫu nhiên trong album A3K56")
    async def random_album(interaction: discord.Interaction):
        view = RandomImageView()
        view.update_image()  # Load the first random image

        # Send an initial message with the first random image and attach the view
        embed = discord.Embed(
            title="Album A3K56 :star:",
            color=discord.Color.green()
        )
        file = discord.File(view.current_image, filename="random_image.png")
        embed.set_image(url="attachment://random_image.png")
        await interaction.response.send_message(embed=embed, file=file, view=view)
    
    # @discordClient.tree.command(name="music", description="Chơi Nhạc")
    # async def play(interaction: discord.Interaction, search: str):
    #     # Kiểm tra người dùng có ở trong kênh thoại không
    #     voice_channel = interaction.user.voice.channel if interaction.user.voice else None
    #     if not voice_channel:
    #         return await interaction.response.send_message("Bạn phải tham gia vào kênh thoại trước!")

    #     # Kết nối bot vào kênh thoại
    #     voice_client = interaction.guild.voice_client
    #     if not voice_client:
    #         voice_client = await voice_channel.connect()

    #     # Sử dụng youtube_dl để tải và phát âm thanh
    #     with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
    #         info = ydl.extract_info(f"ytsearch:{search}", download=False)
    #         url = info['entries'][0]['url']

    #     # Phát âm thanh qua FFMPEG
    #     if voice_client.is_playing():
    #         voice_client.stop()
    #     voice_client.play(discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS))
        
    #     await interaction.response.send_message(f"Đang phát: {info['entries'][0]['title']}")


#-------------------------------------- TIME ----------------------------------------------
    # Lệnh /start để bắt đầu đếm thời gian từ 0
    @discordClient.tree.command(name="start_study", description="Bắt đầu đếm thời gian từ 0 giây")
    async def start(interaction: discord.Interaction):
        global counting_task, start_time

        # Kiểm tra nếu đã có tác vụ đang đếm giờ
        if counting_task and not counting_task.done():
            await interaction.response.send_message("Đang đếm thời gian rồi!", ephemeral=True)
            return

        # Ghi lại thời gian bắt đầu
        start_time = datetime.now()

        # Bắt đầu tác vụ đếm thời gian
        async def counting():
            elapsed_minutes = 0
            while True:
                await asyncio.sleep(60)  # Chờ 1 phút
                elapsed_minutes += 1
                await interaction.followup.send(f"Đã {elapsed_minutes} phút trôi qua!! 🔥🔥. Tiếp tục nào")

        counting_task = discordClient.loop.create_task(counting())
        await interaction.response.send_message("Đã bắt đầu đếm thời gian. Tập trung làm việc nào!! 🔥🔥")

    # Lệnh /end để dừng đếm và hiển thị tổng thời gian đã đếm
    @discordClient.tree.command(name="end_study", description="Kết thúc đếm thời gian")
    async def end(interaction: discord.Interaction):
        global counting_task, start_time

        if not counting_task or counting_task.done():
            await interaction.response.send_message("Chưa bắt đầu đếm thời gian!", ephemeral=True)
            return

        # Hủy tác vụ đếm thời gian
        counting_task.cancel()
        await asyncio.sleep(1)  # Chờ cho tác vụ hoàn tất hủy

        # Tính tổng thời gian
        end_time = datetime.now()
        total_time = end_time - start_time
        hours, remainder = divmod(total_time.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Tạo và gửi embed với tổng thời gian
        embed = discord.Embed(
            title="Kết thúc đếm thời gian!! 🔥🔥",
            description="Tổng thời gian đã học:",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Giờ", value=hours, inline=True)
        embed.add_field(name="Phút", value=minutes, inline=True)
        embed.add_field(name="Giây", value=seconds, inline=True)

        await interaction.response.send_message(embed=embed)

    @discordClient.tree.command(name="start_top", description="Bắt đầu xử lý thời gian hoạt động trong kênh thoại")
    async def start_top(interaction: discord.Interaction):
        global voice_activity

        # Kiểm tra nếu bot đang trong kênh thoại
        if interaction.guild.voice_client is None or not interaction.guild.voice_client.is_connected():
            await interaction.response.send_message("Bot cần phải ở trong kênh thoại để bắt đầu đếm thời gian.")
            return

        # Lấy danh sách các thành viên trong kênh thoại
        voice_channel = interaction.guild.voice_client.channel
        for member in voice_channel.members:
            if member.id not in voice_activity:
                voice_activity[member.id] = {
                    "name": member.display_name,
                    "start_time": datetime.now(),
                    "total_time": 0
                }

            # Bắt đầu kiểm tra camera sau 1 phút
            if member.id not in monitoring_tasks:
                monitoring_tasks[member.id] = discordClient.loop.create_task(check_camera(member))

        await interaction.response.send_message("Đã bắt đầu đếm thời gian cho các thành viên trong kênh thoại. Tập trung học tập lập thành tích nào!! 🔥🔥")
    
    @discordClient.tree.command(name="end_top", description="Kết thúc đếm thời gian và hiển thị bảng xếp hạng")
    async def end_top(interaction: discord.Interaction):
        global voice_activity

        # Cập nhật thời gian hoạt động của các thành viên hiện tại
        for member_id, data in voice_activity.items():
            if data.get("start_time"):
                elapsed_time = (datetime.now() - data["start_time"]).total_seconds()
                voice_activity[member_id]["total_time"] += elapsed_time
                voice_activity[member_id]["start_time"] = None

        # Sắp xếp bảng xếp hạng theo thời gian hoạt động
        sorted_members = sorted(voice_activity.values(), key=lambda x: x["total_time"], reverse=True)

        # Tạo embed để hiển thị bảng xếp hạng
        embed = discord.Embed(
            title="🏆 Bảng Xếp Hạng Hoạt Động Kênh Thoại",
            description="Top thành viên hoạt động trong kênh thoại 🔊",
            color=discord.Color.yellow()
        )

        # Thêm thông tin top thành viên vào embed
        for i, member_data in enumerate(sorted_members[:5], start=1):
            hours, remainder = divmod(member_data["total_time"], 3600)
            minutes, seconds = divmod(remainder, 60)
            embed.add_field(
                name=f"#{i} | {member_data['name']}",
                value=f"Thời gian: {int(hours)} giờ {int(minutes)} phút {int(seconds)} giây",
                inline=False
            )

        await interaction.response.send_message(embed=embed)
        voice_activity.clear() 
    # @discordClient.tree.command(name="top", description="Hiển thị bảng xếp hạng")
    # async def top(interaction: discord.Interaction):
    #     global voice_activity

    #     # Sắp xếp bảng xếp hạng theo thời gian hoạt động
    #     sorted_members = sorted(voice_activity.values(), key=lambda x: x["total_time"], reverse=True)

    #     # Tạo embed để hiển thị bảng xếp hạng tổng quát
    #     embed = discord.Embed(
    #         title="📋 Bảng Xếp Hạng Hoạt Động Máy Chủ Hôm Nay",
    #         description="Thời gian hoạt động của từng thành viên trong kênh thoại 🔊",
    #         color=discord.Color.orange()
    #     )

    #     # Thêm thông tin của tất cả thành viên vào embed
    #     for i, member_data in enumerate(sorted_members, start=1):
    #         hours, remainder = divmod(member_data["total_time"], 3600)
    #         minutes, seconds = divmod(remainder, 60)
    #         embed.add_field(
    #             name=f"#{i} | {member_data['name']}",
    #             value=f"Thời gian: {int(hours)} giờ {int(minutes)} phút {int(seconds)} giây",
    #             inline=False
    #         )

    #     await interaction.response.send_message(embed=embed)
# #-------------------------------------------TIMELAPS-------------------------------------------
#     @discordClient.tree.command(name="timelaps", description="Bắt đầu ghi hình camera của user chỉ định.")
#     async def record(interaction: discord.Interaction, user: discord.User):
#         if interaction.user.voice is None or interaction.user.voice.channel is None:
#             await interaction.response.send_message("Bạn cần tham gia một phòng thoại trước khi dùng lệnh này.", ephemeral=True)
#             return
        
#         voice_channel = interaction.user.voice.channel

#         # Kết nối bot vào voice channel
#         if interaction.guild.voice_client is None:
#             await voice_channel.connect()
        
#         # Bắt đầu ghi hình cho user chỉ định
#         recordings[user.id] = True
#         await interaction.response.send_message(f"Đã bắt đầu ghi hình cho {user.display_name}.")

#         # Thiết lập ghi video từ camera
#         capture = cv2.VideoCapture(0)  # Sử dụng camera mặc định, có thể thay đổi số thứ tự
#         fps = 20  # Tốc độ khung hình bình thường
#         frame_width = int(capture.get(3))
#         frame_height = int(capture.get(4))
#         out = cv2.VideoWriter(f"{user.id}_record.mp4", cv2.VideoWriter_fourcc(*"mp4v"), fps, (frame_width, frame_height))

#         while recordings.get(user.id, False):
#             ret, frame = capture.read()
#             if ret:
#                 out.write(frame)
#             await discordClient.loop.run_in_executor(None, lambda: cv2.waitKey(1))  # Lặp lại mà không cần dừng giữa các khung hình

#         # Giải phóng tài nguyên sau khi kết thúc
#         capture.release()
#         out.release()
#         await interaction.followup.send(f"Đã lưu video cho {user.display_name}.")

#     # Lệnh để kết thúc ghi hình
#     @discordClient.tree.command(name="end_timelaps", description="Kết thúc ghi hình và xuất file cho user chỉ định.")
#     async def end_record(interaction: discord.Interaction, user: discord.User):
#         if not recordings.get(user.id, False):
#             await interaction.response.send_message(f"Không có quá trình ghi hình nào cho {user.display_name}.", ephemeral=True)
#             return
        
#         # Kết thúc quá trình ghi hình
#         recordings[user.id] = False
#         await interaction.response.send_message(f"Đã kết thúc ghi hình cho {user.display_name}.")

#         # Gửi file video cho người dùng
#         output_file = f"{user.id}_record.mp4"
#         await interaction.followup.send(f"Đây là file ghi hình của {user.display_name}.", file=discord.File(output_file))

#         # Xóa file tạm sau khi gửi
#         os.remove(output_file)
# #--------------------------------------------------------------------------------------

    @discordClient.tree.command(name="help", description="Hiện thị các lệnh của bot")
    async def help(interaction: discord.Interaction):
        embed = discord.Embed(
        title="List Các Câu Lệnh của Bot",
        description="""
        :star: **LỆNH CƠ BẢN** \n

        **🤖 ChatAI - (9)**
        - `/chat [message]` Chat với AI 
        - `/draw [prompt][model]` Tạo ảnh vẽ theo lệnh với cấu trúc (Prompt: Lệnh) (Model:Bot)
        - **Khuyên khích:** Chọn Gemini do ChatGPT 4 chưa có tiền:vv (đang bị lỗi)
        - `/switchpersona [persona]` Chuyển đổi chế độ (đang bị lỗi)
                `dan`: DAN 13.5 
                `Smart mode`: AIM 
                `Developer Mode`: software developer 
        - `/private` Chat AI với chế độ Riêng tư
        - `/public` Chat AI với chế độ Public
        - `/replyall` Chat AI chuyển qua chế độ trả lời tất cả
        - `/reset` Xóa lịch sự trò chuyện
        - `/chat-model` Chuyển đổi qua các Model Bot
            `gpt-4`: GPT-4 model (Chưa có tiền chưa dùng được:v)
            `Gemini`: Google gemeni-pro model

        **🔥 Study - (6)**
        - `/start_top` Bắt đầu tính giờ học
        - `/end_top` Thời gian kết thúc giờ học
        - `/tao_phong` Để phòng học thoại mới
        - `/join` Bot vào phòng thoại
        - `/start_time` Đếm ngược thời gian làm bài
        - `/start_study` Bắt đầu đếm thời gian làm bài 
            ( Đi cùng với lệnh **/end** )
        - `/end_study` Kết thúc thời gian làm bài 
            ( Đi cùng với lệnh **/start** )
        - `/top` Hiện thị bảng xếp hạng
        - `/profile` Hiện thị hồ sơ học tập

        **🏆 Other - (2)**
        - `/album` Ngẫu nhiên lấy một bức ảnh trong tuyển tập album A3K56
        - `/addbot` Lấy link mời Bot vào sever
        - `/version` Thông tin cập nhật mới của Bot

        `Lưu Ý`: Sản phẩm chỉ là đồ vọc nên vẫn còn nhiều sai xót, vẫn đang tiếp tục phát triển và nâng cấp trong tương lai..
                                        
""",
        color=discord.Color.red()
        )
        embed.add_field(
            name="Invite Me!",
            value="[Nhấn vào đây để add Bot!](https://discord.com/oauth2/authorize?client_id=1228367902135029830&scope=bot)",
            inline=False
        )
        embed.set_thumbnail(url="https://i.imgur.com/CZFt69d.png")  # Replace with a URL to your desired image

        await interaction.response.send_message(embed=embed)
        logger.info(
            "\x1b[31mSomeone needs help!\x1b[0m")


    @discordClient.tree.command(name="draw", description="Generate an image with the Dall-e-3 model")
    @app_commands.choices(model=[
        app_commands.Choice(name="gemeni", value="gemeni"),
        app_commands.Choice(name="openai", value="openai"),
        app_commands.Choice(name="bing", value="bing"),
        app_commands.Choice(name="dall-e-3", value="dall-e-3"),
    ])
    async def draw(interaction: discord.Interaction, *, prompt: str, model: app_commands.Choice[str]):
        if interaction.user == discordClient.user:
            return

        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : /draw [{prompt}] in ({channel})")

        await interaction.response.defer(thinking=True, ephemeral=discordClient.isPrivate)
        try:
            image_url = await art.draw(model.value, prompt)

            await interaction.followup.send(image_url)

        except Exception as e:
            await interaction.followup.send(
                f'> Something Went Wrong, try again later.\n\nError Message:{e}')
            logger.info(f"\x1b[31m{username}\x1b[0m :{e}")

    @discordClient.tree.command(name="switchpersona", description="Switch between optional chatGPT jailbreaks")
    @app_commands.choices(persona=[
        app_commands.Choice(name="Do Anything Now", value="dan"),
        app_commands.Choice(name="Smart mode(AIM)", value="aim"),
        app_commands.Choice(name="Developer Mode", value="Developer Mode"),
    ])
    async def switchpersona(interaction: discord.Interaction, persona: app_commands.Choice[str]):
        if interaction.user == discordClient.user:
            return

        await interaction.response.defer(thinking=True)
        username = str(interaction.user)
        channel = str(interaction.channel)
        logger.info(
            f"\x1b[31m{username}\x1b[0m : '/switchpersona [{persona.value}]' ({channel})")

        persona = persona.value

        if persona == personas.current_persona:
            await interaction.followup.send(f"> **WARN: Already set to `{persona}` persona**")
        elif persona in personas.PERSONAS:
            try:
                await discordClient.switch_persona(persona)
                personas.current_persona = persona
                await interaction.followup.send(
                f"> **INFO: Switched to `{persona}` persona**")
            except Exception as e:
                await interaction.followup.send(
                    "> ERROR: Something went wrong, try again later! ")
                logger.exception(f"Error while switching persona: {e}")
        else:
            await interaction.followup.send(
                f"> **ERROR: No available persona: `{persona}` 😿**")
            logger.info(
                f'{username} requested an unavailable persona: `{persona}`')


    @discordClient.event
    async def on_message(message):
        if discordClient.is_replying_all == "True":
            if message.author == discordClient.user:
                return
            if discordClient.replying_all_discord_channel_id:
                if message.channel.id == int(discordClient.replying_all_discord_channel_id):
                    username = str(message.author)
                    user_message = str(message.content)
                    discordClient.current_channel = message.channel
                    logger.info(f"\x1b[31m{username}\x1b[0m : '{user_message}' ({discordClient.current_channel})")

                    await discordClient.enqueue_message(message, user_message)
            else:
                logger.exception("replying_all_discord_channel_id not found, please use the command `/replyall` again.")

    TOKEN = os.getenv("DISCORD_BOT_TOKEN")

    discordClient.run(TOKEN)
