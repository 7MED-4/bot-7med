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
    webhook_url: str,
    footer_url: str,
    thumbnail_url: str
):
    data = load_data()
    guild_id = str(interaction.guild.id)
    
    # Save the IDs of the roles, webhook, and photos to our JSON file
    data[guild_id] = {
        "mod_role_id": mod_role.id,
        "warn_1_id": warn_1.id,
        "warn_2_id": warn_2.id,
        "warn_3_id": warn_3.id,
        "webhook_url": webhook_url,
        "footer_url": footer_url,
        "thumbnail_url": thumbnail_url
    }
    save_data(data)
    
    await interaction.response.send_message("✅ Warn system configured successfully with custom photos!", ephemeral=True)

# ==========================================
# COMMAND 2: /gnwarn (UPDATED FOR MULTIPLE USERS & PHOTOS)
# ==========================================
@bot.tree.command(name="gnwarn", description="Warn user(s) using the Garde Nationale system")
@app_commands.describe(
    usernames="Tag one or multiple users using @ (e.g., @John @Jane)",
    from_users="The names or tags of who is issuing this warning"
)
@app_commands.choices(warn_num=[
    app_commands.Choice(name="Warn 1", value=1),
    app_commands.Choice(name="Warn 2", value=2),
    app_commands.Choice(name="Warn 3", value=3),
])
async def gnwarn(
    interaction: discord.Interaction,
    usernames: str,
    warn_num: app_commands.Choice[int],
    reason: str,
    from_users: str
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
    
    # Extract all user IDs from the text string using regex
    user_ids = re.findall(r'<@!?(\d+)>', usernames)
    
    if not user_ids:
        await interaction.followup.send("❌ Error: You must actually tag the users with `@` in the usernames box!")
        return

    warned_successfully = []

    # Loop through every person tagged and process their roles
    for user_id in user_ids:
        member = interaction.guild.get_member(int(user_id))
        if member:
            if role_to_give and role_to_give in member.roles:
                await interaction.followup.send(f"⚠️ Skipped {member.mention}: They already have the **{role_to_give.name}** role.")
                continue
            
            if role_to_give:
                try:
                    await member.add_roles(role_to_give)
                    warned_successfully.append(member.mention)
                except discord.Forbidden:
                    await interaction.followup.send(f"❌ Error: I don't have permission to give roles to {member.mention}.")
            else:
                warned_successfully.append(member.mention)

    # If everyone skipped or errored out, stop the command
    if not warned_successfully:
        await interaction.followup.send("❌ No warnings were sent. Check the errors above.")
        return

    # Combine all successful tags into one string for the embed
    final_usernames = " ".join(warned_successfully)
        
    # Create Embed using the saved photos
    embed = discord.Embed(
        title="WARN",
        description=f"**Username(s) :** {final_usernames}\n**Punishment :** {role_to_give.name if role_to_give else warn_num.name}\n**Reason :** {reason}\n**From :** {from_users}",
        color=0xff0000
    )
    embed.set_thumbnail(url=config.get("thumbnail_url", ""))
    embed.set_footer(text="be careful for your behaviour", icon_url=config.get("footer_url", ""))
    
    # Send via Webhook
    try:
        webhook = discord.Webhook.from_url(config["webhook_url"], client=bot)
        await webhook.send(
            content=f"**Users Warned:** {final_usernames}", 
            embed=embed
        )
        
        await interaction.followup.send(f"✅ Warn successfully sent for {len(warned_successfully)} user(s)!")
    except Exception as e:
        await interaction.followup.send(f"❌ Failed to send webhook. Check your URL. Error: {e}")


# ==========================================
# COMMAND 3: /join
# ==========================================
@bot.tree.command(name="join", description="Make the bot join a specific voice channel")
@app_commands.describe(channel="Select the voice channel for the bot to join")
async def join_vc(interaction: discord.Interaction, channel: discord.VoiceChannel):
    # Acknowledge the command quickly so Discord doesn't time out
    await interaction.response.defer()

    # Check if the bot is already connected to voice in this server
    voice_client = interaction.guild.voice_client

    try:
        if voice_client and voice_client.is_connected():
            # If it is already in a channel, just move it to the new one
            await voice_client.move_to(channel)
            await interaction.followup.send(f"🏃‍♂️ Moved to {channel.mention}!")
        else:
            # If it is not in a channel, connect it
            await channel.connect()
            await interaction.followup.send(f"✅ Successfully joined {channel.mention}!")
            
    except discord.Forbidden:
        await interaction.followup.send("❌ Error: I don't have the 'Connect' permission for that specific channel.")
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {e}")

        # Run the bot using the token from the .env file
bot.run(os.getenv('DISCORD_TOKEN'))