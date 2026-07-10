import discord
from discord.ext import commands
from discord import app_commands
import json
import os
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




        # Run the bot using the token from the .env file
bot.run(os.getenv('DISCORD_TOKEN'))