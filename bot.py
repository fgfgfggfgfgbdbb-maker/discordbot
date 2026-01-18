import discord
from keep_alive import keep_alive
from discord.ext import commands, tasks
from discord import app_commands
import json
import time
import os
from datetime import datetime, timedelta

# ===================== CONFIG =====================

CONFIG_FILE = "config.json"

with open(CONFIG_FILE) as f:
    data = json.load(f)

TOKEN = data["TOKEN"]
LOG_CHANNEL = data["LOG_CHANNEL"]

if "WHITELIST" not in data:
    data["WHITELIST"] = []

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

LIMIT = 5

# ===================== TRACKERS =====================

ban_tracker = {}
kick_tracker = {}
webhook_tracker = {}
message_tracker = {}
mod_actions = {}
join_log = []
backups = {}

# ===================== UTILITIES =====================

def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)


async def log(guild, message):
    channel = guild.get_channel(LOG_CHANNEL)
    if channel:
        await channel.send(message)


def is_whitelisted(user_id):
    return user_id in data["WHITELIST"]


def track_mod(user):
    mod_actions[str(user)] = mod_actions.get(str(user), 0) + 1


async def punish(guild, user, reason):
    if is_whitelisted(user.id):
        return

    try:
        await guild.ban(user, reason=f"ANTI-NUKE: {reason}")
        await log(guild, f"🚨 ANTI-NUKE: Banned {user} for {reason}")
    except Exception as e:
        print("Punish failed:", e)

# ===================== STARTUP =====================

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot online as {bot.user}")
    backup_server.start()

# ===================== BACKUP SYSTEM =====================

@tasks.loop(minutes=5)
async def backup_server():
    for guild in bot.guilds:
        backups[guild.id] = {
            "channels": [(c.name, str(c.type)) for c in guild.channels],
            "roles": [(r.name, r.permissions.value) for r in guild.roles]
        }

# ===================== INFO COMMANDS =====================

@bot.tree.command(name="serverinfo")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild

    embed = discord.Embed(title=f"{g.name} - Info", color=discord.Color.blue())
    embed.add_field(name="Members", value=g.member_count)
    embed.add_field(name="Owner", value=g.owner)
    embed.add_field(name="Roles", value=len(g.roles))
    embed.add_field(name="Channels", value=len(g.channels))

    if g.icon:
        embed.set_thumbnail(url=g.icon.url)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="roleinfo")
async def roleinfo(interaction: discord.Interaction, role: discord.Role):

    embed = discord.Embed(title=f"Role: {role.name}", color=role.color)
    embed.add_field(name="ID", value=role.id)
    embed.add_field(name="Members", value=len(role.members))
    embed.add_field(name="Permissions", value=str(role.permissions.value))

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="botstats")
async def botstats(interaction: discord.Interaction):

    embed = discord.Embed(title="Bot Stats", color=discord.Color.purple())
    embed.add_field(name="Servers", value=len(bot.guilds))
    embed.add_field(name="Users", value=sum(g.member_count for g in bot.guilds))

    await interaction.response.send_message(embed=embed)

# ===================== MODERATION COMMANDS =====================

@bot.tree.command(name="lockdown")
async def lockdown(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Admins only.", ephemeral=True)

    for channel in interaction.guild.channels:
        try:
            await channel.set_permissions(
                interaction.guild.default_role, send_messages=False
            )
        except:
            pass

    await interaction.response.send_message("🔒 Server locked down.")
    await log(interaction.guild, f"Lockdown by {interaction.user}")


@bot.tree.command(name="unlockdown")
async def unlockdown(interaction: discord.Interaction):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Admins only.", ephemeral=True)

    for channel in interaction.guild.channels:
        try:
            await channel.set_permissions(
                interaction.guild.default_role, send_messages=True
            )
        except:
            pass

    await interaction.response.send_message("🔓 Server unlocked.")
    await log(interaction.guild, f"Unlockdown by {interaction.user}")

# ===================== BAN COMMANDS =====================

@bot.tree.command(name="baninfo")
async def baninfo(interaction: discord.Interaction, user: discord.User):

    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("No permission.", ephemeral=True)

    try:
        ban = await interaction.guild.fetch_ban(user)
        reason = ban.reason or "No reason"
        banned = True
    except:
        banned = False
        reason = "Not banned"

    embed = discord.Embed(title="Ban Info", color=discord.Color.red())
    embed.add_field(name="User", value=str(user))
    embed.add_field(name="Banned", value=str(banned))
    embed.add_field(name="Reason", value=reason)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tempban")
async def tempban(interaction: discord.Interaction, user: discord.Member, minutes: int):

    if not interaction.user.guild_permissions.ban_members:
        return await interaction.response.send_message("No permission.", ephemeral=True)

    await interaction.guild.ban(user, reason="Tempban")

    await interaction.response.send_message(f"{user} banned for {minutes} minutes.")
    await log(interaction.guild, f"{user} tempbanned by {interaction.user}")

    await discord.utils.sleep_until(datetime.utcnow() + timedelta(minutes=minutes))

    try:
        await interaction.guild.unban(user)
        await log(interaction.guild, f"{user} automatically unbanned.")
    except:
        pass

# ===================== WHITELIST =====================

@bot.tree.command(name="whitelist_add")
async def whitelist_add(interaction: discord.Interaction, user: discord.User):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Admins only.", ephemeral=True)

    data["WHITELIST"].append(user.id)
    save_config()

    await interaction.response.send_message(f"{user} added to whitelist.")


@bot.tree.command(name="whitelist_remove")
async def whitelist_remove(interaction: discord.Interaction, user: discord.User):

    if user.id in data["WHITELIST"]:
        data["WHITELIST"].remove(user.id)
        save_config()

    await interaction.response.send_message(f"{user} removed from whitelist.")


@bot.tree.command(name="whitelist_list")
async def whitelist_list(interaction: discord.Interaction):

    text = "\n".join([f"<@{u}>" for u in data["WHITELIST"]])
    await interaction.response.send_message(f"Whitelisted:\n{text}")

# ===================== SECURITY SYSTEMS =====================

@bot.event
async def on_member_ban(guild, user):

    logs = await guild.audit_logs(limit=1, action=discord.AuditLogAction.ban).flatten()
    if logs:
        mod = logs[0].user

        if is_whitelisted(mod.id):
            return

        ban_tracker[mod.id] = ban_tracker.get(mod.id, 0) + 1

        if ban_tracker[mod.id] >= LIMIT:
            await punish(guild, mod, "Mass banning")


@bot.event
async def on_member_remove(member):

    logs = await member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick).flatten()

    if logs:
        mod = logs[0].user

        if is_whitelisted(mod.id):
            return

        kick_tracker[mod.id] = kick_tracker.get(mod.id, 0) + 1

        if kick_tracker[mod.id] >= LIMIT:
            await punish(member.guild, mod, "Mass kicking")

# ===================== ANTI SPAM =====================

@bot.event
async def on_message(message):

    if message.author.bot:
        return

    user = message.author.id
    now = time.time()

    message_tracker.setdefault(user, []).append(now)
    message_tracker[user] = [t for t in message_tracker[user] if now - t < 5]

    if len(message_tracker[user]) > 5:
        try:
            until = datetime.utcnow() + timedelta(minutes=5)
            await message.author.timeout(until, reason="Spam")
            await message.channel.send(f"{message.author} muted for spam.")
        except:
            pass

    await bot.process_commands(message)

# ===================== LOGGING =====================

@bot.event
async def on_message_delete(message):
    if message.guild:
        await log(message.guild, f"🗑 Deleted: {message.author}: {message.content}")


@bot.event
async def on_member_join(member):
    await log(member.guild, f"📥 {member} joined")


@bot.event
async def on_member_remove(member):
    await log(member.guild, f"📤 {member} left")

# ===================== RUN =====================
keep_alive()
bot.run(TOKEN)
