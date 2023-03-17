import discord
from discord.ext import commands
from discord import app_commands

class ChannelSelector(discord.ui.ChannelSelect):
    def __init__(self, bot, c_type):
        if c_type in ("vid", "bid"):
            super().__init__(placeholder="Select a channel", channel_types=[discord.ChannelType.voice])
        elif c_type in ("catid",):
            super().__init__(placeholder="Select a category", channel_types=[discord.ChannelType.category])
        elif c_type in ("confid",):
            super().__init__(placeholder="Select a channel", channel_types=[discord.ChannelType.text])
        self.bot = bot
        self.c_type = c_type

    async def callback(self, interaction: discord.Interaction):
        async with self.bot.pool.acquire() as con:
            if self.c_type == "vid":
                embed = discord.Embed(title="Setup", description="Please select the voice channel to inherit permissions from.")
                await interaction.response.edit_message(embed=embed, view=SetupView(self.bot, "bid"))
            elif self.c_type == "bid":
                embed = discord.Embed(title="Setup", description="Please select the category to create the voice channels in")
                await interaction.response.edit_message(embed=embed, view=SetupView(self.bot, "catid"))
            elif self.c_type == "catid":
                embed = discord.Embed(title="Setup", description="Please select the channel to send the configuration message in.")
                await interaction.response.edit_message(embed=embed, view=SetupView(self.bot, "confid"))
            else:
                embed = discord.Embed(title="Setup", description="Setup complete!")
                await interaction.response.edit_message(embed=embed, view=None)
                await interaction.message.delete(delay=5)
            await con.execute(f"UPDATE config SET {self.c_type} = $1 WHERE gid = $2", self.values[0].id, interaction.guild.id)
            self.view.stop()

class RoleSelector(discord.ui.RoleSelect):
    def __init__(self, bot, age):
        super().__init__(placeholder="Select a role")
        self.bot = bot
        self.age = age

    async def callback(self, interaction: discord.Interaction):
        async with self.bot.pool.acquire() as con:
            await con.execute(f"UPDATE config SET role_{self.age} = $1 WHERE gid = $2", self.values[0].id, interaction.guild.id)
            embed = discord.Embed(title="Setup", description="Please select the role to inherit permissions from.")
            await interaction.response.edit_message(embed=embed, view=SetupView(self.bot, "rid"))
            self.view.stop()

class SetupView(discord.ui.View):
    def __init__(self, bot, c_type):
        super().__init__()
        self.timeout = 30
        self.bot = bot
        self.c_type = type
        self.add_item(ChannelSelector(bot, c_type))

class SetupModal(discord.ui.Modal, title="VoiceCommand setup"):
    # TODO modals can't have more than 5 components
    voice_channel = discord.ui.ChannelSelect(placeholder="Select a voice setup channel", channel_types=[discord.ChannelType.voice])
    base_cahnnel = discord.ui.ChannelSelect(placeholder="Select a base permissions channel", channel_types=[discord.ChannelType.voice])
    category = discord.ui.ChannelSelect(placeholder="Select a category", channel_types=[discord.ChannelType.category])
    config_channel = discord.ui.ChannelSelect(placeholder="Select a config message channel", channel_types=[discord.ChannelType.text])
    role_18 = discord.ui.RoleSelect(placeholder="Select role for 18+")
    role_22 = discord.ui.RoleSelect(placeholder="Select role for 22+")
    role_30 = discord.ui.RoleSelect(placeholder="Select role for 30+")

    def __init__(self, bot):
        super().__init__(timeout=0)
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        async with self.bot.pool.acquire() as con:
            row = await con.fetchrow("SELECT * FROM config WHERE gid = $1", interaction.guild.id)
            if row and row["confid"] and row["mid"]:
                try:
                    msg = await self.bot.get_channel(row["confid"]).fetch_message(row["mid"])
                    await msg.delete()
                except (discord.NotFound, TypeError):
                    pass
            await con.execute("UPDATE config SET vid = $1, bid = $2, catid = $3, confid = $4, role_18 = $5, role_22 = $6, role_30 = $7 WHERE gid = $8",
                            self.voice_channel.values[0].id, self.base_cahnnel.values[0].id, self.category.values[0].id, self.config_channel.values[0].id,
                            self.role_18.values[0].id, self.role_22.values[0].id, self.role_30.values[0].id, interaction.guild.id)
            await interaction.response.send_message("Setup complete!", ephemeral=True)

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    @commands.is_owner()
    async def sync(self, ctx: commands.Context):
        res = await self.bot.tree.sync()
        await ctx.reply(f"synced: {res}")

    @app_commands.command(name="setup", description="Setup the bot in your server")
    async def setup(self, interaction: discord.Interaction):
        async with self.bot.pool.acquire() as con:
            await con.execute("INSERT INTO config (gid) VALUES ($1) ON CONFLICT (gid) DO NOTHING", interaction.guild.id)
            await interaction.response.send_modal(SetupModal(self.bot))

async def setup(bot):
    await bot.add_cog(Moderation(bot))