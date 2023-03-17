import discord
from discord.ext import commands
from discord.ext import tasks

class Channel_setup_menu(discord.ui.Modal, title="Voice channel setup"):
    member_limit = discord.ui.TextInput(label="Member limit (0-99)", min_length=1, max_length=2, default="0")

    def __init__(self, bot, config, channel):
        super().__init__(timeout=0)
        self.bot = bot
        self.config = config
        self.channel = channel

    async def on_submit(self, interaction: discord.Interaction):
        try:
            limit = int(self.member_limit.value)
            if limit < 0 or limit > 99:
                raise ValueError
        except ValueError:
            await interaction.response.send_message("Invalid member limit", ephemeral=True, delete_after=5)
            return
        member = interaction.guild.get_member(interaction.user.id)
        if member and member.voice and member.voice.channel.id == self.config["vid"]:
            async with self.bot.pool.acquire() as con:
                row = await con.fetchrow("SELECT * FROM channels WHERE uid = $1", member.id)
                channel = member.guild.get_channel(row["vid"]) if row else None
                if not channel:
                    base_channel = member.guild.get_channel(self.config["bid"])
                    category = member.guild.get_channel(self.config["catid"])
                    if not base_channel or not category:
                        await member.move_to(channel=None)
                    perms = base_channel.overwrites
                    new_channel = await member.guild.create_voice_channel(name="Personal voice channel", overwrites=perms, category=category, user_limit=limit)
                    await member.move_to(new_channel)
                    await interaction.response.defer()
                    await con.execute("INSERT INTO channels (vid, uid) VALUES ($1, $2) ON CONFLICT (vid) DO NOTHING", new_channel.id, member.id)
                else:
                    await member.move_to(channel)
                    await interaction.response.defer()
        elif self.channel:
            await interaction.response.defer()
            await self.channel.edit(user_limit=limit)
        else:
            await interaction.response.send_message("You are not in the setup voice channel", ephemeral=True, delete_after=5)
            return


class Setup_buttons(discord.ui.Button):
    def __init__(self, bot):
        super().__init__(label="Click to set up voice channel", style=discord.ButtonStyle.primary, emoji="🔊")
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        member: discord.Member = interaction.guild.get_member(interaction.user.id)
        if not member:
            await interaction.response.send_message("Something went wrong, please try again later.", ephemeral=True, delete_after=5)
            return
        elif not member.voice:
            await interaction.response.send_message("You are not in the setup voice channel", ephemeral=True, delete_after=5)
            return
        async with self.bot.pool.acquire() as con:
            config = await con.fetchrow("SELECT * FROM config WHERE gid = $1", interaction.guild.id)
            channel = await con.fetchrow("SELECT * FROM channels WHERE uid = $1", member.id)
            channel = member.guild.get_channel(channel["vid"]) if channel else None
            if not config:
                await interaction.response.send_message("The server owner has not set up the voice channel", ephemeral=True, delete_after=5)
                return
            if member.voice.channel.id != config["vid"] and (not channel or member.voice.channel.id != channel.id):
                await interaction.response.send_message("You are not in the setup voice channel", ephemeral=True, delete_after=5)
                return

            await interaction.response.send_modal(Channel_setup_menu(self.bot, config, channel))

class Channel_setup(discord.ui.View):
    def __init__(self, bot):
        super().__init__()
        self.timeout = 0
        self.bot = bot
        self.add_item(Setup_buttons(bot))

class Channel_manager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_config_message.start()

    @tasks.loop(minutes=5)
    async def check_config_message(self):
        async with self.bot.pool.acquire() as con:
            configs = await con.fetch("SELECT * FROM config")
            for config in configs:
                guild = self.bot.get_guild(config["gid"])
                if not guild:
                    continue
                channel = guild.get_channel(config["confid"])
                if not channel:
                    continue
                try:
                    message = await channel.fetch_message(config["mid"] if config["mid"] else 0)
                except discord.NotFound:
                    message = None
                if not message:
                    m = await channel.send("Setup", view=Channel_setup(self.bot))
                    await con.execute("UPDATE config SET mid = $1 WHERE gid = $2", m.id, guild.id)
                else:
                    await message.edit(view=Channel_setup(self.bot))

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return
        async with self.bot.pool.acquire() as con:
            config = await con.fetchrow("SELECT * FROM config WHERE gid = $1", member.guild.id)
            if not config:
                return

            c = await con.fetchrow("SELECT * FROM channels WHERE uid = $1", member.id)
            if before.channel and before.channel.id == config["vid"]:
                return
            elif before.channel and c and before.channel.id == c["vid"]:
                members = [m for m in before.channel.members if not m.bot]
                if len(members) == 0:
                    await before.channel.delete()
                    await con.execute("DELETE FROM channels WHERE vid = $1", before.channel.id)

async def setup(bot):
    await bot.add_cog(Channel_manager(bot))