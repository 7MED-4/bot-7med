import discord
from discord.ext import commands
from discord import app_commands
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
# COMMANDS 7-9: interview accept/reject system
# (its own storage file, independent from /setupwarn and /configristictedroles)
# ==========================================
INTERVIEW_DATA_FILE = "/app/data/interview_config.json"


def load_interview_data():
    os.makedirs(os.path.dirname(INTERVIEW_DATA_FILE), exist_ok=True)
    if os.path.exists(INTERVIEW_DATA_FILE):
        with open(INTERVIEW_DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_interview_data(data):
    os.makedirs(os.path.dirname(INTERVIEW_DATA_FILE), exist_ok=True)
    with open(INTERVIEW_DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


@bot.tree.command(name="setupinterview", description="Configure the interview accept/reject system (Admins only)")
@app_commands.default_permissions(administrator=True)  # Only admins can see/use this command
async def setupinterview(
    interaction: discord.Interaction,
    interview_role: discord.Role,
    role_accept: discord.Role,
    role_reject: discord.Role,
    accept_msg: str,
    reject_msg: str,
    channel: discord.TextChannel,
    reject_time: int,
    under_age: discord.Role,
    no_mic: discord.Role,
):
    # Extra safety check in case a server has manually changed the command's permissions
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You must be an administrator to use this command.", ephemeral=True)
        return

    data = load_interview_data()
    guild_id = str(interaction.guild.id)
    # Preserve any in-progress reject timers if this is a re-configuration
    active_rejections = data.get(guild_id, {}).get("active_rejections", {})

    data[guild_id] = {
        "interview_role_id": interview_role.id,
        "role_accept_id": role_accept.id,
        "role_reject_id": role_reject.id,
        "accept_msg": accept_msg,
        "reject_msg": reject_msg,
        "channel_id": channel.id,
        "reject_time_hours": reject_time,
        "under_age_role_id": under_age.id,
        "no_mic_role_id": no_mic.id,
        "active_rejections": active_rejections,
    }
    save_interview_data(data)

    await interaction.response.send_message(
        f"✅ Interview system configured. Only {interview_role.mention} can use /interviewaccept and /interviewreject.",
        ephemeral=True,
    )


def _get_interview_config(interaction: discord.Interaction):
    """Returns (config, error_message). error_message is None if everything checks out."""
    data = load_interview_data()
    config = data.get(str(interaction.guild.id))
    if not config:
        return None, "❌ Interview system not set up! Run /setupinterview first."

    interview_role_id = config["interview_role_id"]
    has_role = any(role.id == interview_role_id for role in interaction.user.roles)
    if not has_role:
        return None, "❌ You do not have the required role to use this command."

    return config, None


@bot.tree.command(name="interviewaccept", description="Accept an interview candidate")
async def interviewaccept(
    interaction: discord.Interaction,
    username: discord.Member,
    whitelister: discord.Member,
    by: discord.Member,
):
    config, error = _get_interview_config(interaction)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return

    role_accept = interaction.guild.get_role(config["role_accept_id"])
    if role_accept:
        try:
            await username.add_roles(role_accept)
        except discord.Forbidden:
            await interaction.response.send_message("❌ I don't have permission to give that role.", ephemeral=True)
            return

    channel = interaction.guild.get_channel(config["channel_id"])
    content = (
        f"Whitelister : {whitelister.mention}\n"
        f"{username.mention} **{config['accept_msg']}** By: {by.mention}"
    )

    if channel:
        await channel.send(content, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

    await interaction.response.send_message(f"✅ {username.mention} has been accepted.", ephemeral=True)


@bot.tree.command(name="interviewreject", description="Reject an interview candidate")
@app_commands.choices(reason=[
    app_commands.Choice(name="Come back after 12h", value="come_back_12h"),
    app_commands.Choice(name="Under Age", value="under_age"),
    app_commands.Choice(name="No Mic", value="no_mic"),
])
async def interviewreject(
    interaction: discord.Interaction,
    username: discord.Member,
    reason: app_commands.Choice[str],
    whitelister: discord.Member,
    by: discord.Member,
):
    config, error = _get_interview_config(interaction)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return

    # Build the role list: role_reject always applies, plus under_age/no_mic depending on reason
    roles_to_add = []
    role_reject = interaction.guild.get_role(config["role_reject_id"])
    if role_reject:
        roles_to_add.append(role_reject)

    if reason.value == "under_age":
        under_age_role = interaction.guild.get_role(config.get("under_age_role_id"))
        if under_age_role:
            roles_to_add.append(under_age_role)
    elif reason.value == "no_mic":
        no_mic_role = interaction.guild.get_role(config.get("no_mic_role_id"))
        if no_mic_role:
            roles_to_add.append(no_mic_role)

    try:
        await username.add_roles(*roles_to_add)
    except discord.Forbidden:
        await interaction.response.send_message("❌ I don't have permission to give one of those roles.", ephemeral=True)
        return

    # Start the reject-role protection timer
    data = load_interview_data()
    guild_id = str(interaction.guild.id)
    guild_config = data[guild_id]
    guild_config.setdefault("active_rejections", {})
    guild_config["active_rejections"][str(username.id)] = time.time() + (config["reject_time_hours"] * 3600)
    data[guild_id] = guild_config
    save_interview_data(data)

    channel = interaction.guild.get_channel(config["channel_id"])
    content = (
        f"Whitelister : {whitelister.mention}\n"
        f"{username.mention} **{config['reject_msg']} ❌ {reason.name} ❌ bonne chance** By:{by.mention}"
    )

    if channel:
        await channel.send(content, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))

    await interaction.response.send_message(f"✅ {username.mention} has been rejected.", ephemeral=True)


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
                                    f"**Time :** {discord.utils.format_dt(now, style='F')}"
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


async def handle_interview_reject_protection(before: discord.Member, after: discord.Member):
    removed_roles = [r for r in before.roles if r not in after.roles]
    if not removed_roles:
        return

    data = load_interview_data()
    guild_id = str(after.guild.id)
    config = data.get(guild_id)
    if not config:
        return

    role_reject_id = config.get("role_reject_id")
    if not role_reject_id:
        return

    if not any(r.id == role_reject_id for r in removed_roles):
        return

    # Give Discord's audit log a moment to record the change
    await asyncio.sleep(1)

    try:
        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
            if entry.target.id != after.id:
                continue

            remover = after.guild.get_member(entry.user.id)
            is_admin = bool(remover and remover.guild_permissions.administrator)

            if is_admin:
                # An administrator removed it — let it stick, clear any tracked timer
                active = config.get("active_rejections", {})
                active.pop(str(after.id), None)
                config["active_rejections"] = active
                data[guild_id] = config
                save_interview_data(data)
            else:
                # Anyone else removed it — reapply, no matter what the timer says
                role_reject = after.guild.get_role(role_reject_id)
                if role_reject:
                    try:
                        await after.add_roles(role_reject, reason="Rejected role can only be removed by an administrator")
                    except discord.Forbidden:
                        pass
            break
    except discord.Forbidden:
        # Bot is missing the "View Audit Log" permission
        pass


@bot.event
async def on_member_update(before: discord.Member, after: discord.Member):
    # Nothing to do if roles didn't change
    if before.roles == after.roles:
        return

    await handle_restricted_role_addition(before, after)
    await handle_interview_reject_protection(before, after)


# Run the bot using the token from the .env file
bot.run(os.getenv('DISCORD_TOKEN'))