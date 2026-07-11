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
@app_commands.default_permissions(administrator=True) # Only admins can see this command
async def setupwarn(
    interaction: discord.Interaction, 
    mod_role: discord.Role,
    warn_1: discord.Role,
    warn_2: discord.Role,
    warn_3: discord.Role,
    webhook_url: str
):
    data = load_data()
    guild_id = str(interaction.guild.id)
    
    # Save the IDs of the roles and the webhook URL to our JSON file
    data[guild_id] = {
        "mod_role_id": mod_role.id,
        "warn_1_id": warn_1.id,
        "warn_2_id": warn_2.id,
        "warn_3_id": warn_3.id,
        "webhook_url": webhook_url
    }
    save_data(data)
    
    await interaction.response.send_message("✅ Warn system configured successfully! The data is saved safely on Railway.", ephemeral=True)


# ==========================================
# COMMAND 2: /gnwarn (UPDATED WITH ROLE CHECK)
# ==========================================
@bot.tree.command(name="gnwarn", description="Warn a user using the Garde Nationale system")
@app_commands.choices(warn_num=[
    app_commands.Choice(name="Warn 1", value=1),
    app_commands.Choice(name="Warn 2", value=2),
    app_commands.Choice(name="Warn 3", value=3),
])
async def gnwarn(
    interaction: discord.Interaction,
    username: discord.Member,
    warn_num: app_commands.Choice[int],
    reason: str,
    from_user: discord.Member
):
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

    await interaction.response.defer(ephemeral=True)

    # Determine role
    role_id_to_give = None
    if warn_num.value == 1: role_id_to_give = config["warn_1_id"]
    elif warn_num.value == 2: role_id_to_give = config["warn_2_id"]
    elif warn_num.value == 3: role_id_to_give = config["warn_3_id"]
        
    role_to_give = interaction.guild.get_role(role_id_to_give)
    
    if role_to_give:
        # NEW: Check if the user already has the role
        if role_to_give in username.roles:
            await interaction.followup.send(f"❌ Aborted: {username.mention} already has the **{role_to_give.name}** role! No webhook was sent.")
            return
            
        try:
            await username.add_roles(role_to_give)
        except discord.Forbidden:
            await interaction.followup.send("❌ Error: I don't have permission to give that role. Move my bot role higher in the server settings!")
            return
            
    # Create Embed
    embed = discord.Embed(
        title="WARN",
        description=f"**Username :** {username.mention}\n**Punishement :** {role_to_give.name if role_to_give else warn_num.name}\n**Reason :** {reason}\n**From :** {from_user.mention}",
        color=0xff0000
    )
    embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1524529124310257685/1525128235669655642/Ecusson_garde_nationale_Tunisie.svg.png")
    embed.set_footer(text="be careful for your behaviour", icon_url="https://cdn.discordapp.com/attachments/1524529124310257685/1525128002491383989/warn-removebg-preview.png")
    
    # Send via Webhook
    try:
        webhook = discord.Webhook.from_url(config["webhook_url"], client=bot)
        await webhook.send(
            content=f"**User Warned:** {username.mention}", 
            embed=embed
        )
        
        await interaction.followup.send(f"✅ Warn successfully sent for {username.display_name}!")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to send webhook. Check your URL. Error: {e}")


# ==========================================
# COMMAND 3: /join
# ==========================================
@bot.tree.command(name="join")
async def join(interaction: discord.Interaction, channel: discord.VoiceChannel):
    await interaction.response.defer()

    try:
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            vc = await channel.connect(timeout=30, reconnect=False)

        await interaction.followup.send(f"Joined {channel.mention}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        await interaction.followup.send(f"Error:\n```{type(e).__name__}: {e}```")

        # Run the bot using the token from the .env file
bot.run(os.getenv('DISCORD_TOKEN'))