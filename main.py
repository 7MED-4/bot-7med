import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
import json
import os
import re
import time
from dotenv import load_dotenv

# Load the token from the .env file
load_dotenv()

# We need the members intent to assign roles to users
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

# This points directly to your permanent Railway cloud hard drive folder
DATA_FILE = "/app/data/warn_config.json"

# Fallback thumbnail if a server hasn't set a custom photo yet
DEFAULT_THUMBNAIL = "https://cdn.discordapp.com/attachments/1524529124310257685/1525128235669655642/Ecusson_garde_nationale_Tunisie.svg.png"

# Order + labels used everywhere we need to display/resolve warn options
WARN_OPTION_ORDER = ["warn_1", "warn_2", "warn_3", "on_probation"]
WARN_OPTION_LABELS = {
    "warn_1": "Warn 1",
    "warn_2": "Warn 2",
    "warn_3": "Warn 3",
    "on_probation": "On Probation",
}
# Maps a warn option to the config key holding its role id
WARN_OPTION_CONFIG_KEY = {
    "warn_1": "warn_1_id",
    "warn_2": "warn_2_id",
    "warn_3": "warn_3_id",
    "on_probation": "on_probation_id",
}


def load_data():
    # Automatically create the /app/data folder if it doesn't exist yet
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data):
    # Automatically create the /app/data folder if it doesn't exist yet
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)

    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

    # Re-register the persistent duty panel view so its buttons keep working after a restart
    bot.add_view(DutyPanelView())
    bot.add_view(ProfilePanelView())

    try:
        # Sync the slash commands globally so they appear in Discord
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


# ==========================================
# COMMAND 1: /setupwarn
# ==========================================
@bot.tree.command(name="setupwarn", description="Configure the warning system (Admins only)")
@app_commands.default_permissions(administrator=True)  # Only admins can see this command
async def setupwarn(
    interaction: discord.Interaction,
    mod_role: discord.Role,
    warn_1: discord.Role,
    warn_2: discord.Role,
    warn_3: discord.Role,
    webhook_url: str,
    photo: str,
    on_probation: discord.Role,
):
    data = load_data()
    guild_id = str(interaction.guild.id)

    # Save the IDs of the roles, the webhook URL, the thumbnail photo,
    # and the "on probation" role to our JSON file
    data[guild_id] = {
        "mod_role_id": mod_role.id,
        "warn_1_id": warn_1.id,
        "warn_2_id": warn_2.id,
        "warn_3_id": warn_3.id,
        "webhook_url": webhook_url,
        "photo_url": photo,
        "on_probation_id": on_probation.id,
    }
    save_data(data)

    await interaction.response.send_message("✅ Warn system configured successfully! The data is saved safely on Railway.", ephemeral=True)


# ==========================================
# COMMAND 2: /gnwarn — interactive multi-select version
# ==========================================
class ReasonModal(discord.ui.Modal, title="Set Warn Reason"):
    reason_input = discord.ui.TextInput(
        label="Reason",
        style=discord.TextStyle.paragraph,
        placeholder="Why is this warn being issued?",
        required=True,
        max_length=500,
    )

    def __init__(self, view: "GNWarnView"):
        super().__init__()
        self.view_ref = view
        if view.reason:
            self.reason_input.default = view.reason

    async def on_submit(self, interaction: discord.Interaction):
        self.view_ref.reason = str(self.reason_input.value)
        await interaction.response.edit_message(content=self.view_ref.status_text(), view=self.view_ref)


class GNWarnView(discord.ui.View):
    """
    Interactive panel shown after /gnwarn is run.
    Lets the moderator pick multiple usernames, multiple "from" users,
    and multiple warn options (Warn 1/2/3 + On Probation).
    """

    def __init__(self, invoker: discord.Member, guild: discord.Guild, config: dict):
        super().__init__(timeout=180)
        self.invoker = invoker
        self.guild = guild
        self.config = config
        self.reason = ""

        self.selected_usernames: list[discord.Member] = []
        self.selected_from_users: list[discord.Member] = []
        self.selected_warns: list[str] = []

        self.username_select.placeholder = "Select user(s) to warn"
        self.from_user_select.placeholder = "Select who is issuing the warn"
        self.warn_select.placeholder = "Select warn level(s) / On Probation"

    def status_text(self) -> str:
        reason_display = self.reason if self.reason else "*(not set — use the reason dropdown below)*"
        return (
            "Fill out the panel below, then hit **Submit**:\n"
            f"**Reason:** {reason_display}"
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker.id:
            await interaction.response.send_message("❌ Only the person who ran /gnwarn can use this panel.", ephemeral=True)
            return False
        return True

    # ---- Username multi-select ----
    @discord.ui.select(cls=discord.ui.UserSelect, min_values=1, max_values=25, row=0)
    async def username_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_usernames = [m for m in select.values if isinstance(m, discord.Member)]
        await interaction.response.defer()

    # ---- From-user multi-select ----
    @discord.ui.select(cls=discord.ui.UserSelect, min_values=1, max_values=25, row=1)
    async def from_user_select(self, interaction: discord.Interaction, select: discord.ui.UserSelect):
        self.selected_from_users = [m for m in select.values if isinstance(m, discord.Member)]
        await interaction.response.defer()

    # ---- Warn level multi-select ----
    @discord.ui.select(
        placeholder="Select warn level(s) / On Probation",
        min_values=1,
        max_values=4,
        row=2,
        options=[
            discord.SelectOption(label="Warn 1", value="warn_1"),
            discord.SelectOption(label="Warn 2", value="warn_2"),
            discord.SelectOption(label="Warn 3", value="warn_3"),
            discord.SelectOption(label="On Probation", value="on_probation"),
        ],
    )
    async def warn_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        self.selected_warns = select.values
        await interaction.response.defer()

    # ---- Reason (select panel, opens a text modal — no standalone button) ----
    @discord.ui.select(
        placeholder="Select to set the reason",
        min_values=1,
        max_values=1,
        row=3,
        options=[discord.SelectOption(label="📝 Click to type a reason", value="set_reason")],
    )
    async def reason_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        await interaction.response.send_modal(ReasonModal(self))

    # ---- Submit ----
    @discord.ui.button(label="Submit", style=discord.ButtonStyle.green, row=4)
    async def submit(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Basic validation
        if not self.reason:
            await interaction.response.send_message("❌ Set a reason first.", ephemeral=True)
            return
        if not self.selected_usernames:
            await interaction.response.send_message("❌ Pick at least one user to warn.", ephemeral=True)
            return
        if not self.selected_from_users:
            await interaction.response.send_message("❌ Pick at least one 'from' user.", ephemeral=True)
            return
        if not self.selected_warns:
            await interaction.response.send_message("❌ Pick at least one warn option.", ephemeral=True)
            return

        # "On Probation" can only be picked alongside at least one Warn X
        has_warn_level = any(w in ("warn_1", "warn_2", "warn_3") for w in self.selected_warns)
        if "on_probation" in self.selected_warns and not has_warn_level:
            await interaction.response.send_message(
                "❌ 'On Probation' can only be selected together with at least one Warn level.",
                ephemeral=True,
            )
            return

        # Warn levels must be picked "in a row" — e.g. Warn 1 + Warn 2 is fine,
        # but Warn 1 + Warn 3 (skipping Warn 2) is not.
        warn_numbers = sorted(int(w.split("_")[1]) for w in self.selected_warns if w in ("warn_1", "warn_2", "warn_3"))
        if warn_numbers and (warn_numbers[-1] - warn_numbers[0] + 1) != len(warn_numbers):
            await interaction.response.send_message(
                "❌ Warn levels must be consecutive (e.g. Warn 1 + Warn 2 is fine, Warn 1 + Warn 3 is not).",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        # Keep a stable display order: Warn 1, Warn 2, Warn 3, On Probation
        ordered_warns = [w for w in WARN_OPTION_ORDER if w in self.selected_warns]

        # Resolve the actual roles to give out
        roles_to_give = []
        for w in ordered_warns:
            role_id = self.config.get(WARN_OPTION_CONFIG_KEY[w])
            role = self.guild.get_role(role_id) if role_id else None
            if role:
                roles_to_give.append(role)

        # Verify none of the selected users already have any of the selected roles.
        # If any do, abort the whole submission (no roles changed, no webhook sent).
        conflicts = []
        for member in self.selected_usernames:
            for role in roles_to_give:
                if role in member.roles:
                    conflicts.append(f"{member.display_name} already has **{role.name}**")

        if conflicts:
            await interaction.followup.send(
                "❌ Aborted — the following already apply:\n" + "\n".join(conflicts),
                ephemeral=True,
            )
            return

        # Apply roles to every selected username
        forbidden_users = []
        for member in self.selected_usernames:
            for role in roles_to_give:
                try:
                    await member.add_roles(role)
                except discord.Forbidden:
                    forbidden_users.append(member.display_name)

        # Build embed text
        punishment_text = ", ".join(WARN_OPTION_LABELS[w] for w in ordered_warns)
        username_text = ", ".join(m.mention for m in self.selected_usernames)
        from_text = ", ".join(m.mention for m in self.selected_from_users)

        embed = discord.Embed(
            title="WARN",
            description=(
                f"**Username :** {username_text}\n"
                f"**Punishement :** {punishment_text}\n"
                f"**Reason :** {self.reason}\n"
                f"**From :** {from_text}"
            ),
            color=0xff0000,
        )
        embed.set_thumbnail(url=self.config.get("photo_url", DEFAULT_THUMBNAIL))
        embed.set_footer(
            text="be careful for your behaviour",
            icon_url="https://cdn.discordapp.com/attachments/1524529124310257685/1525128002491383989/warn-removebg-preview.png",
        )

        # Send via Webhook
        try:
            webhook = discord.Webhook.from_url(self.config["webhook_url"], client=bot)
            await webhook.send(content=f"**User(s) Warned:** {username_text}", embed=embed)
            result_msg = f"✅ Warn successfully sent for {username_text}!"
        except Exception as e:
            result_msg = f"❌ Failed to send webhook. Check your URL. Error: {e}"

        if forbidden_users:
            result_msg += f"\n❌ Missing permission to role: {', '.join(forbidden_users)}"

        # Disable the view now that it's been used
        for item in self.children:
            item.disabled = True
        await interaction.edit_original_response(content=result_msg, view=self)
        self.stop()


@bot.tree.command(name="gnwarn", description="Warn one or more users using the Garde Nationale system")
async def gnwarn(interaction: discord.Interaction):
    data = load_data()
    guild_id = str(interaction.guild.id)

    if guild_id not in data:
        await interaction.response.send_message("❌ System not set up! Run /setupwarn first.", ephemeral=True)
        return

    config = data[guild_id]

    # Permission Check — only the configured mod_role can use this command
    mod_role_id = config["mod_role_id"]
    has_role = any(role.id == mod_role_id for role in interaction.user.roles)

    if not has_role:
        await interaction.response.send_message("❌ You do not have the required role.", ephemeral=True)
        return

    view = GNWarnView(invoker=interaction.user, guild=interaction.guild, config=config)
    await interaction.response.send_message(
        view.status_text(),
        view=view,
        ephemeral=True,
    )


# ==========================================
# COMMAND 3: /join
# ==========================================
@bot.tree.command(name="join", description="Make the bot join your current voice channel")
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
async def join_vc(interaction: discord.Interaction):
    # Extra safety check in case a server has manually changed the command's permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    # Check if the user who typed the command is actually in a voice channel
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ You must be in a voice channel to use this command!", ephemeral=True)
        return

    await interaction.response.defer()

    # Get the exact channel the user is currently sitting in
    channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client

    try:
        # If the bot is already in a channel, move it to the user's channel
        if voice_client and voice_client.is_connected():
            await voice_client.move_to(channel)
            await interaction.followup.send(f"🏃‍♂️ Moved to {channel.mention}!")
        # If the bot is not in a channel, connect normally
        else:
            await channel.connect(reconnect=False)
            await interaction.followup.send(f"✅ Successfully joined {channel.mention}!")

    except discord.Forbidden:
        await interaction.followup.send("❌ Error: I don't have the 'Connect' permission for your channel.")
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {e}")


# ==========================================
# COMMAND 4: /configristictedroles
# (fully independent from /setupwarn — its own storage file)
# ==========================================
RESTRICT_DATA_FILE = "/app/data/restrict_config.json"


def load_restrict_data():
    os.makedirs(os.path.dirname(RESTRICT_DATA_FILE), exist_ok=True)
    if os.path.exists(RESTRICT_DATA_FILE):
        with open(RESTRICT_DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_restrict_data(data):
    os.makedirs(os.path.dirname(RESTRICT_DATA_FILE), exist_ok=True)
    with open(RESTRICT_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


@bot.tree.command(
    name="configristictedroles",
    description="Set a restricted role and its log channel (Admins only)",
)
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
async def configristictedroles(
    interaction: discord.Interaction,
    roles_restricted: discord.Role,
    channel_logs: discord.TextChannel,
):
    # Extra safety check in case a server has manually changed the command's permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    data = load_restrict_data()
    guild_id = str(interaction.guild.id)
    config = data.setdefault(guild_id, {"restricted_role_ids": [], "log_channel_id": None})

    restricted = config.get("restricted_role_ids", [])
    if roles_restricted.id in restricted:
        restricted.remove(roles_restricted.id)
        role_msg = f"🔓 {roles_restricted.mention} removed from the restricted list — its holders can self-add roles again."
    else:
        restricted.append(roles_restricted.id)
        role_msg = f"🔒 {roles_restricted.mention} added to the restricted list — any role its holders self-add will now be automatically removed."

    config["restricted_role_ids"] = restricted
    config["log_channel_id"] = channel_logs.id
    data[guild_id] = config
    save_restrict_data(data)

    await interaction.response.send_message(
        f"{role_msg}\n📋 Removals will be logged in {channel_logs.mention}.",
        ephemeral=True,
    )


# ==========================================
# COMMAND 5: /members
# ==========================================
@bot.tree.command(name="members", description="List all members who have a specific role")
async def members(interaction: discord.Interaction, role: discord.Role):
    await interaction.response.defer()

    role_members = sorted(role.members, key=lambda m: m.display_name.lower())

    if not role_members:
        await interaction.followup.send(f"No members currently have the {role.mention} role.")
        return

    # Split the member list into chunks that fit Discord's embed description limit (4096 chars)
    chunks = []
    current_chunk = ""
    for member in role_members:
        line = f"{member.mention}\n"
        if len(current_chunk) + len(line) > 4000:
            chunks.append(current_chunk)
            current_chunk = line
        else:
            current_chunk += line
    if current_chunk:
        chunks.append(current_chunk)

    embed_color = role.color if role.color.value else 0x5865F2

    for i, chunk in enumerate(chunks):
        title = f"Members with {role.name} ({len(role_members)})" if i == 0 else f"Members with {role.name} (cont.)"
        embed = discord.Embed(title=title, description=chunk, color=embed_color)
        await interaction.followup.send(embed=embed)


# ==========================================
# COMMAND 6: /roleping
# ==========================================
@bot.tree.command(name="roleping", description="Ping every member who has a specific role (Admins only)")
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
async def roleping(interaction: discord.Interaction, role: discord.Role):
    # Extra safety check in case a server has manually changed the command's permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    role_members = role.members
    if not role_members:
        await interaction.response.send_message(f"No members currently have the {role.mention} role.")
        return

    mentions = ", ".join(member.mention for member in role_members)
    content = f"**Role Members : {role.mention}**\n{mentions}"

    # Discord messages are capped at 2000 characters — trim the list if it's too long
    # for a single message, rather than splitting into several messages.
    if len(content) > 2000:
        content = content[:1970] + "\n... *(list truncated — too many members for one message)*"

    await interaction.response.send_message(content, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))


# ==========================================
# COMMAND 7: /setupduty
# (own storage file, independent from the rest)
# ==========================================
DUTY_DATA_FILE = "/app/data/duty_config.json"


def load_duty_data():
    os.makedirs(os.path.dirname(DUTY_DATA_FILE), exist_ok=True)
    if os.path.exists(DUTY_DATA_FILE):
        with open(DUTY_DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_duty_data(data):
    os.makedirs(os.path.dirname(DUTY_DATA_FILE), exist_ok=True)
    with open(DUTY_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


class DutyPanelView(discord.ui.View):
    """
    Persistent view (timeout=None, static custom_id) attached to the duty panel embed.
    Works across bot restarts as long as it's re-registered via bot.add_view() in on_ready.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Start Duty", style=discord.ButtonStyle.success, emoji="🟢", custom_id="duty_start_button")
    async def start_duty(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_duty_data()
        config = data.get(str(interaction.guild.id))
        if not config:
            await interaction.response.send_message("❌ Duty system not set up! Run /setupduty first.", ephemeral=True)
            return

        duty_channel = interaction.guild.get_channel(config["duty_channel_id"])
        now = discord.utils.utcnow()
        content = (
            "➳ Service Status: **ON**\n"
            f"➳ Officer: {interaction.user.mention}\n"
            f"➳ Time: `{now.strftime('%H:%M')}`"
        )

        try:
            webhook = discord.Webhook.from_url(config["webhook_url"], client=interaction.client)
            await webhook.send(content=content)
        except Exception as e:
            await interaction.response.send_message(
               f"❌ Failed to send the webhook.\nError: {e}",
               ephemeral=True
            )
            return

        await interaction.response.send_message("✅ Duty started.", ephemeral=True)

    @discord.ui.button(label="End Duty", style=discord.ButtonStyle.danger, emoji="🔴", custom_id="duty_end_button")
    async def end_duty(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_duty_data()
        config = data.get(str(interaction.guild.id))
        if not config:
            await interaction.response.send_message("❌ Duty system not set up! Run /setupduty first.", ephemeral=True)
            return

        duty_channel = interaction.guild.get_channel(config["duty_channel_id"])
        now = discord.utils.utcnow()
        content = (
            "➳ Service Status: **OFF**\n"
            f"➳ Officer: {interaction.user.mention}\n"
            f"➳ Time: `{now.strftime('%H:%M')}`"
        )

        try:
            webhook = discord.Webhook.from_url(config["webhook_url"], client=interaction.client)
            await webhook.send(content=content)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to send the webhook.\nError: {e}",
                ephemeral=True
            )
            return
        await interaction.response.send_message("✅ Duty ended.", ephemeral=True)


@bot.tree.command(name="setupduty", description="Send the GN duty panel and set the log channel (Admins only)")
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
async def setupduty(
    interaction: discord.Interaction,
    send_panel: discord.TextChannel,
    duty_channel: discord.TextChannel,
    webhook_url: str 
):
    # Extra safety check in case a server has manually changed the command's permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    data = load_duty_data()
    data[str(interaction.guild.id)] = {"duty_channel_id": duty_channel.id, "webhook_url": webhook_url}
    save_duty_data(data)

    embed = discord.Embed(
        title="🛡️ GN DUTY SYSTEM",
        description="Use the buttons below to register the start or end of your Grade Nationale shift (Duty).",
        color=0x2b2d42,
    )

    await send_panel.send(embed=embed, view=DutyPanelView())
    await interaction.response.send_message(
        f"✅ Duty panel sent in {send_panel.mention}. Duty logs will go to {duty_channel.mention}.",
        ephemeral=True,
    )


# ==========================================
# COMMAND 8: /setupprofile
# (own storage file, independent from the rest)
# ==========================================
PROFILE_DATA_FILE = "/app/data/profile_config.json"


def load_profile_data():
    os.makedirs(os.path.dirname(PROFILE_DATA_FILE), exist_ok=True)
    if os.path.exists(PROFILE_DATA_FILE):
        with open(PROFILE_DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_profile_data(data):
    os.makedirs(os.path.dirname(PROFILE_DATA_FILE), exist_ok=True)
    with open(PROFILE_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


async def resolve_roblox_id(query: str, session: aiohttp.ClientSession):
    """Accepts a username, a numeric user ID, or a profile URL and returns the Roblox user ID."""
    query = query.strip()

    # Profile URL, e.g. https://www.roblox.com/users/12345/profile
    match = re.search(r"/users/(\d+)", query)
    if match:
        return int(match.group(1))

    # Plain numeric ID
    if query.isdigit():
        return int(query)

    # Otherwise treat it as a username
    async with session.post(
        "https://users.roblox.com/v1/usernames/users",
        json={"usernames": [query], "excludeBannedUsers": False},
    ) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        if data.get("data"):
            return data["data"][0]["id"]
    return None


class RobloxLookupModal(discord.ui.Modal, title="Roblox Account Lookup"):
    lookup_input = discord.ui.TextInput(
        label="Username, Profile Link, or User ID",
        placeholder="Enter Username, ID, or Profile URL...",
        required=True,
        max_length=200,
    )

    def __init__(self, webhook_url: str, guild_id: int):
        super().__init__()
        self.webhook_url = webhook_url
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        query = str(self.lookup_input.value)

        async with aiohttp.ClientSession() as session:
            roblox_id = await resolve_roblox_id(query, session)
            if not roblox_id:
                await interaction.followup.send(
                    "❌ Couldn't find that Roblox account. Double check the username, ID, or profile link.",
                    ephemeral=True,
                )
                return

            try:
                async with session.get(f"https://users.roblox.com/v1/users/{roblox_id}") as resp:
                    if resp.status != 200:
                        await interaction.followup.send("❌ Couldn't find that Roblox account.", ephemeral=True)
                        return
                    user_data = await resp.json()

                friends_count = "N/A"
                async with session.get(f"https://friends.roblox.com/v1/users/{roblox_id}/friends/count") as resp:
                    if resp.status == 200:
                        friends_data = await resp.json()
                        friends_count = friends_data.get("count", "N/A")

                avatar_url = None
                async with session.get(
                    f"https://thumbnails.roblox.com/v1/users/avatar?userIds={roblox_id}&size=420x420&format=Png&isCircular=false"
                ) as resp:
                    if resp.status == 200:
                        thumb_data = await resp.json()
                        if thumb_data.get("data"):
                            avatar_url = thumb_data["data"][0].get("imageUrl")
            except Exception as e:
                await interaction.followup.send(f"❌ Error fetching Roblox data: {e}", ephemeral=True)
                return

        display_name = user_data.get("displayName", "Unknown")
        username = user_data.get("name", "Unknown")
        profile_url = f"https://www.roblox.com/users/{roblox_id}/profile"

        # Remember this Discord -> Roblox link so /profile can look it up later
        data = load_profile_data()
        guild_config = data.setdefault(str(self.guild_id), {})
        guild_config.setdefault("links", {})[str(interaction.user.id)] = roblox_id
        save_profile_data(data)

        embed = discord.Embed(
            title="🎮 Roblox User Information",
            description=f"**{display_name}**",
            color=0x5865F2,
        )
        embed.set_author(name=f"Linked by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        embed.add_field(name="👤 Display Name", value=display_name, inline=True)
        embed.add_field(name="🏷️ Username", value=f"@{username}", inline=True)
        embed.add_field(name="🆔 User ID", value=str(roblox_id), inline=True)
        embed.add_field(name="👥 Friends", value=str(friends_count), inline=False)
        embed.add_field(name="🔗 Profile Link", value=f"[Click Here to View Profile]({profile_url})", inline=False)
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        embed.timestamp = discord.utils.utcnow()

        content = f"USER : {interaction.user.mention} , Roblox user : {username}"

        try:
            webhook = discord.Webhook.from_url(self.webhook_url, client=interaction.client)
            await webhook.send(content=content, embed=embed)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to send via webhook. Check your URL. Error: {e}", ephemeral=True)
            return

        await interaction.followup.send("✅ Your Roblox profile has been shared!", ephemeral=True)


class ProfilePanelView(discord.ui.View):
    """
    Persistent view (timeout=None, static custom_id) attached to the profile panel embed.
    Works across bot restarts as long as it's re-registered via bot.add_view() in on_ready.
    """

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="My Profile", style=discord.ButtonStyle.primary, emoji="🎮", custom_id="profile_lookup_button")
    async def my_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = load_profile_data()
        config = data.get(str(interaction.guild.id))
        if not config:
            await interaction.response.send_message("❌ Profile system not set up! Run /setupprofile first.", ephemeral=True)
            return

        await interaction.response.send_modal(RobloxLookupModal(config["webhook_url"], interaction.guild.id))


@bot.tree.command(name="setupprofile", description="Send the Roblox profile lookup panel (Admins only)")
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
async def setupprofile(
    interaction: discord.Interaction,
    panel_send: discord.TextChannel,
    profil_channel: discord.TextChannel,
    webhook: str,
    game_link: str,
):
    # Extra safety check in case a server has manually changed the command's permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    # game_link must be a normal Roblox game URL (e.g. roblox.com/games/<placeId>/name) —
    # share links (roblox.com/share?code=...) can't be reliably resolved server-side.
    match = re.search(r"/games/(\d+)", game_link)
    if not match:
        await interaction.response.send_message(
            "❌ Couldn't find a place ID in that link. Use the normal game URL "
            "(e.g. `https://www.roblox.com/games/1818/Classic-Crossroads`), not a share link.",
            ephemeral=True,
        )
        return
    place_id = int(match.group(1))

    data = load_profile_data()
    existing = data.get(str(interaction.guild.id), {})
    data[str(interaction.guild.id)] = {
        "profil_channel_id": profil_channel.id,
        "webhook_url": webhook,
        "target_place_id": place_id,
        "links": existing.get("links", {}),
    }
    save_profile_data(data)

    embed = discord.Embed(
        title="📍 Roblox Profiles",
        description="Welcome! Click the button below to share your Roblox profile .",
        color=0x2b2d42,
    )
    embed.add_field(name="Supported Inputs:", value="• Username\n• User ID\n• Profile URL Link", inline=False)
    embed.set_footer(text="Roblox Profile")

    await panel_send.send(embed=embed, view=ProfilePanelView())
    await interaction.response.send_message(
        f"✅ Profile panel sent in {panel_send.mention}. Lookups will be posted in {profil_channel.mention}.",
        ephemeral=True,
    )


async def send_profile_lookup(interaction: discord.Interaction, config: dict, roblox_id: int, mention_line: str | None):
    """Shared logic for both /profile discord and /profile roblox: fetch Roblox data and reply with the embed."""
    if not interaction.response.is_done():
        await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"https://users.roblox.com/v1/users/{roblox_id}") as resp:
                if resp.status != 200:
                    await interaction.followup.send("❌ Couldn't find that Roblox account.", ephemeral=True)
                    return
                user_data = await resp.json()

            avatar_url = None
            async with session.get(
                f"https://thumbnails.roblox.com/v1/users/avatar?userIds={roblox_id}&size=420x420&format=Png&isCircular=false"
            ) as resp:
                if resp.status == 200:
                    thumb_data = await resp.json()
                    if thumb_data.get("data"):
                        avatar_url = thumb_data["data"][0].get("imageUrl")

            # Live presence check — this can only tell us if they're playing the
            # target game RIGHT NOW, not whether they've ever played it before.
            playing_status = "❌"
            try:
                async with session.post(
                    "https://presence.roblox.com/v1/presence/users",
                    json={"userIds": [roblox_id]},
                ) as resp:
                    if resp.status == 200:
                        presence_data = await resp.json()
                        presences = presence_data.get("userPresences", [])
                        if presences:
                            p = presences[0]
                            target_place_id = config.get("target_place_id")
                            if p.get("userPresenceType") == 2 and p.get("placeId") == target_place_id:
                                playing_status = "✅"
            except Exception:
                pass
        except Exception as e:
            await interaction.followup.send(f"❌ Error fetching Roblox data: {e}", ephemeral=True)
            return

    display_name = user_data.get("displayName", "Unknown")
    username = user_data.get("name", "Unknown")
    profile_url = f"https://www.roblox.com/users/{roblox_id}/profile"

    embed = discord.Embed(
        description=f"**[{display_name}]({profile_url})**",
        color=0x5865F2,
    )
    embed.add_field(name="👤 Display Name", value=display_name, inline=True)
    embed.add_field(name="🏷️ Username", value=f"@{username}", inline=True)
    embed.add_field(name="🆔 User ID", value=str(roblox_id), inline=True)
    embed.add_field(name="🎮 The user are playing", value=playing_status, inline=True)
    if avatar_url:
        embed.set_thumbnail(url=avatar_url)
    embed.timestamp = discord.utils.utcnow()

    content = mention_line if mention_line else "*(no linked Discord user found)*"

    await interaction.followup.send(content=content, embed=embed)


profile_group = app_commands.Group(name="profile", description="Look up a Roblox profile")


@profile_group.command(name="discord", description="Look up a Roblox profile by Discord user")
async def profile_discord(interaction: discord.Interaction, discord_user: discord.Member):
    data = load_profile_data()
    config = data.get(str(interaction.guild.id))
    if not config:
        await interaction.response.send_message("❌ Profile system not set up! Run /setupprofile first.", ephemeral=True)
        return

    links = config.get("links", {})
    roblox_id = links.get(str(discord_user.id))
    if not roblox_id:
        await interaction.response.send_message(
            f"❌ No linked Roblox account found for {discord_user.mention}. They need to use the profile panel first.",
            ephemeral=True,
        )
        return

    await send_profile_lookup(interaction, config, roblox_id, discord_user.mention)


@profile_group.command(name="roblox", description="Look up a Roblox profile by username, ID, or link")
async def profile_roblox(interaction: discord.Interaction, roblox_query: str):
    data = load_profile_data()
    config = data.get(str(interaction.guild.id))
    if not config:
        await interaction.response.send_message("❌ Profile system not set up! Run /setupprofile first.", ephemeral=True)
        return

    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        roblox_id = await resolve_roblox_id(roblox_query, session)
    if not roblox_id:
        await interaction.followup.send("❌ Couldn't find that Roblox account.", ephemeral=True)
        return

    # Reverse lookup — is this Roblox ID linked to any known Discord user in this server?
    mention_line = None
    links = config.get("links", {})
    for discord_id, linked_roblox_id in links.items():
        if linked_roblox_id == roblox_id:
            member = interaction.guild.get_member(int(discord_id))
            if member:
                mention_line = member.mention
            break

    await send_profile_lookup(interaction, config, roblox_id, mention_line)


bot.tree.add_command(profile_group)


# ==========================================
# COMMANDS 9-13: cross-server connect system
# (own storage file, independent from the rest)
#
# Vocabulary used below:
#   "source server" = the server holding all the members (your "server 1")
#   "child server"  = a server linked to a source server (your "server 2/3/4...")
#   A child server always has exactly one source. A source can have many children.
# ==========================================
CONNECT_DATA_FILE = "/app/data/connect_config.json"


def load_connect_data():
    os.makedirs(os.path.dirname(CONNECT_DATA_FILE), exist_ok=True)
    if os.path.exists(CONNECT_DATA_FILE):
        with open(CONNECT_DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_connect_data(data):
    os.makedirs(os.path.dirname(CONNECT_DATA_FILE), exist_ok=True)
    with open(CONNECT_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


async def other_server_autocomplete(interaction: discord.Interaction, current: str):
    """Lists every server the bot shares, except the one the command is being run in."""
    choices = []
    for guild in bot.guilds:
        if guild.id == interaction.guild.id:
            continue
        if current.lower() in guild.name.lower():
            choices.append(app_commands.Choice(name=guild.name, value=str(guild.id)))
    return choices[:25]


async def connected_server_autocomplete(interaction: discord.Interaction, current: str):
    """Lists servers connected to the one the command is being run in (as source or as child)."""
    data = load_connect_data()
    this_id = interaction.guild.id
    connected_ids = set()

    this_config = data.get(str(this_id))
    if this_config:
        connected_ids.add(this_config["source_guild_id"])

    for child_id, cfg in data.items():
        if cfg.get("source_guild_id") == this_id:
            connected_ids.add(int(child_id))

    choices = []
    for guild_id in connected_ids:
        guild = bot.get_guild(guild_id)
        if guild and current.lower() in guild.name.lower():
            choices.append(app_commands.Choice(name=guild.name, value=str(guild_id)))
    return choices[:25]


async def source_role_autocomplete(interaction: discord.Interaction, current: str):
    """Lists roles from THIS server's linked source server (for /newmemberrole)."""
    data = load_connect_data()
    config = data.get(str(interaction.guild.id))
    if not config:
        return []
    source_guild = bot.get_guild(config["source_guild_id"])
    if not source_guild:
        return []
    choices = []
    for role in source_guild.roles:
        if role.is_default():
            continue
        if current.lower() in role.name.lower():
            choices.append(app_commands.Choice(name=role.name, value=str(role.id)))
    return choices[:25]


@bot.tree.command(name="connect", description="Link this server to a source server for role logging (Admins only)")
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
@app_commands.autocomplete(servers=other_server_autocomplete)
async def connect(interaction: discord.Interaction, servers: str, logging: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    source_guild_id = int(servers)
    if source_guild_id == interaction.guild.id:
        await interaction.response.send_message("❌ A server can't be linked to itself.", ephemeral=True)
        return

    source_guild = bot.get_guild(source_guild_id)
    if not source_guild:
        await interaction.response.send_message("❌ The bot isn't in that server.", ephemeral=True)
        return

    data = load_connect_data()
    guild_id = str(interaction.guild.id)
    config = data.setdefault(guild_id, {"role_mappings": []})
    config["source_guild_id"] = source_guild_id
    config["log_channel_id"] = logging.id
    config.setdefault("role_mappings", [])
    data[guild_id] = config
    save_connect_data(data)

    await interaction.response.send_message(
        f"✅ This server is now linked to **{source_guild.name}**. New-member logs will be posted in {logging.mention}.",
        ephemeral=True,
    )


@bot.tree.command(name="disconnect", description="Unlink this server from a connected server (Admins only)")
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
@app_commands.autocomplete(servers=connected_server_autocomplete)
async def disconnect(interaction: discord.Interaction, servers: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    target_id = int(servers)
    data = load_connect_data()
    guild_id = str(interaction.guild.id)
    removed_something = False

    # This server was the child pointing to that source
    config = data.get(guild_id)
    if config and config.get("source_guild_id") == target_id:
        del data[guild_id]
        removed_something = True

    # This server was the source that a child pointed to
    if str(target_id) in data and data[str(target_id)].get("source_guild_id") == interaction.guild.id:
        del data[str(target_id)]
        removed_something = True

    if removed_something:
        save_connect_data(data)
        await interaction.response.send_message("✅ Connection removed.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No connection found with that server.", ephemeral=True)


@bot.tree.command(name="connectlist", description="Show servers connected to this one")
async def connectlist(interaction: discord.Interaction):
    data = load_connect_data()
    this_id = interaction.guild.id
    lines = []

    this_config = data.get(str(this_id))
    if this_config:
        source_guild = bot.get_guild(this_config["source_guild_id"])
        source_name = source_guild.name if source_guild else f"Unknown server ({this_config['source_guild_id']})"
        lines.append(f"**Linked to (as a child of):** {source_name}")

    children = []
    for child_id, cfg in data.items():
        if cfg.get("source_guild_id") == this_id:
            child_guild = bot.get_guild(int(child_id))
            children.append(child_guild.name if child_guild else f"Unknown server ({child_id})")
    if children:
        lines.append("**Servers linked to this one (as children):**\n" + "\n".join(f"• {name}" for name in children))

    if not lines:
        await interaction.response.send_message("❌ This server isn't connected to any other server.", ephemeral=True)
        return

    embed = discord.Embed(title="🔗 Connected Servers", description="\n\n".join(lines), color=0x5865F2)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="newmemberrole", description="Add/remove an auto-role mapping from the source server's roles (Admins only)")
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
@app_commands.autocomplete(source_role=source_role_autocomplete)
async def newmemberrole(interaction: discord.Interaction, source_role: str, target_role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    data = load_connect_data()
    guild_id = str(interaction.guild.id)
    config = data.get(guild_id)
    if not config:
        await interaction.response.send_message("❌ This server isn't connected to a source server yet! Run /connect first.", ephemeral=True)
        return

    source_guild = bot.get_guild(config["source_guild_id"])
    source_role_id = int(source_role)
    source_role_obj = source_guild.get_role(source_role_id) if source_guild else None
    source_role_name = source_role_obj.name if source_role_obj else source_role

    mappings = config.get("role_mappings", [])
    existing = next(
        (m for m in mappings if m["source_role_id"] == source_role_id and m["target_role_id"] == target_role.id),
        None,
    )

    if existing:
        mappings.remove(existing)
        msg = f"🔓 Removed mapping: **{source_role_name}** (source) → {target_role.mention} (this server)."
    else:
        mappings.append({"source_role_id": source_role_id, "target_role_id": target_role.id})
        msg = f"🔒 Added mapping: **{source_role_name}** (source) → {target_role.mention} (this server)."

    config["role_mappings"] = mappings
    data[guild_id] = config
    save_connect_data(data)

    await interaction.response.send_message(msg, ephemeral=True)


@bot.tree.command(name="scanmember", description="Show a member's roles in a connected server (Admins only)")
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
@app_commands.autocomplete(server_connected_list=connected_server_autocomplete)
async def scanmember(interaction: discord.Interaction, user: discord.Member, server_connected_list: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    target_guild = bot.get_guild(int(server_connected_list))
    if not target_guild:
        await interaction.response.send_message("❌ That server isn't reachable right now.", ephemeral=True)
        return

    target_member = target_guild.get_member(user.id)
    if not target_member:
        await interaction.response.send_message(f"❌ {user.mention} isn't a member of **{target_guild.name}**.", ephemeral=True)
        return

    # Use plain role names, not mentions — a role mention only resolves within
    # the server it belongs to, so a mention for another server's role would
    # render as "unknown role" for anyone viewing it.
    role_names = [f"• {r.name}" for r in target_member.roles if not r.is_default()]
    embed = discord.Embed(
        title=f"Roles in {target_guild.name}",
        description="\n".join(role_names) if role_names else "*No roles*",
        color=0x5865F2,
    )
    embed.set_author(name=str(target_member), icon_url=target_member.display_avatar.url)
    await interaction.response.send_message(embed=embed, ephemeral=True)


async def handle_connect_member_join(member: discord.Member):
    """When someone joins a child server, log + apply mapped roles based on their roles in the source server."""
    data = load_connect_data()
    config = data.get(str(member.guild.id))
    if not config:
        return

    source_guild = bot.get_guild(config["source_guild_id"])
    log_channel = member.guild.get_channel(config["log_channel_id"])

    source_member = source_guild.get_member(member.id) if source_guild else None

    if not source_member:
        content = f"📥 {member.mention} joined — not currently a member of **{source_guild.name if source_guild else 'the source server'}**."
        if log_channel:
            await log_channel.send(content)
        return

    role_names = ", ".join(r.name for r in source_member.roles if not r.is_default()) or "No roles"
    content = (
        f"📥 {member.mention} joined this server.\n"
        f"➳ Roles in **{source_guild.name}** : {role_names}"
    )
    if log_channel:
        await log_channel.send(content)

    # Apply any configured role mappings
    source_role_ids = {r.id for r in source_member.roles}
    roles_to_add = []
    for mapping in config.get("role_mappings", []):
        if mapping["source_role_id"] in source_role_ids:
            target_role = member.guild.get_role(mapping["target_role_id"])
            if target_role:
                roles_to_add.append(target_role)

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Auto-role from connected source server")
        except discord.Forbidden:
            pass


async def handle_restricted_role_addition(before: discord.Member, after: discord.Member):
    added_roles = [r for r in after.roles if r not in before.roles]
    if not added_roles:
        return

    data = load_restrict_data()
    config = data.get(str(after.guild.id))
    if not config:
        return

    restricted_ids = config.get("restricted_role_ids", [])
    if not restricted_ids:
        return

    # Only relevant if the member still holds one of the restricted roles
    if not any(r.id in restricted_ids for r in after.roles):
        return

    # Give Discord's audit log a moment to record the change
    await asyncio.sleep(1)

    try:
        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
            # Only revert if the member gave the role(s) to themselves
            if entry.target.id == after.id and entry.user.id == after.id:
                try:
                    await after.remove_roles(*added_roles, reason="Restricted role: self-added role blocked")

                    # Log the action as an embed in the configured channel (no webhook)
                    log_channel_id = config.get("log_channel_id")
                    if log_channel_id:
                        log_channel = after.guild.get_channel(log_channel_id)
                        if log_channel:
                            now = discord.utils.utcnow()
                            roles_text = ", ".join(r.name for r in added_roles)
                            embed = discord.Embed(
                                title="Self-Added Role Removed",
                                description=(
                                    f"**User :** {after.mention} ({after})\n"
                                    f"**Role(s) Added :** {roles_text}\n"
                                    f"**Time :** {now.strftime('%H:%M')}"
                                ),
                                color=0xff9900,
                            )
                            embed.timestamp = now
                            try:
                                await log_channel.send(embed=embed)
                            except discord.Forbidden:
                                pass
                except discord.Forbidden:
                    pass
                break
    except discord.Forbidden:
        # Bot is missing the "View Audit Log" permission
        pass


@bot.event
async def on_member_join(member: discord.Member):
    await handle_connect_member_join(member)


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    # Nothing to do if roles didn't change
    if before.roles == after.roles:
        return

    await handle_restricted_role_addition(before, after)


# Run the bot using the token from the .env file
bot.run(os.getenv('DISCORD_TOKEN'))