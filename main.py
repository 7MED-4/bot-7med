import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# 1. Load the environment variables from your specific file
load_dotenv('bot.env') 
# Note: If you ever rename the file to just '.env', you can just use load_dotenv()

# 2. Get the token safely
TOKEN = os.getenv('DISCORD_TOKEN')

# 3. Setup Intents
intents = discord.Intents.default()
intents.message_content = True 

# 4. Initialize the bot
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'⚡ System online. Logged in as {bot.user.name}')
    print('------')

@bot.command()
async def ping(ctx):
    await ctx.send('Pong! 🏓')

# 5. Run the bot using the hidden token
bot.run(TOKEN)