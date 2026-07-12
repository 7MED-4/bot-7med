import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import re
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
        reason_display = self.reason if self.reason else "*(not set — click **Set Reason**)*"
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

    # ---- Reason (opens a text modal, same as picking an option on the other panels) ----
    @discord.ui.button(label="Set Reason", style=discord.ButtonStyle.blurple, row=3)
    async def set_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
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

        # Apply roles to every selected username
        already_had = []
        forbidden_users = []
        for member in self.selected_usernames:
            for role in roles_to_give:
                if role in member.roles:
                    already_had.append(f"{member.display_name} already had {role.name}")
                    continue
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

        if already_had:
            result_msg += "\n⚠️ " + " | ".join(already_had)
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

    # Permission Check
    mod_role_id = config["mod_role_id"]
    has_role = any(role.id == mod_role_id for role in interaction.user.roles)

    if not has_role and not interaction.user.guild_permissions.administrator:
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
async def join_vc(interaction: discord.Interaction):
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


# Run the bot using the token from the .env file
bot.run(os.getenv('DISCORD_TOKEN'))