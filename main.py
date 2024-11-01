# This example requires the 'message_content' intent.
import enum
import os
from dotenv import load_dotenv
import discord
from discord import app_commands
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# loads environment variables from file
load_dotenv()

# sets the GUILD_ID environment variable for the testing server
MY_GUILD = discord.Object(id=os.environ['GUILD_ID'])

# client wrapper class for the habot client of the discord.py Client
class HabotClient(discord.Client):
    def __init__(self, intents: discord.Intents):
        super().__init__(intents=intents)

        self.tree = app_commands.CommandTree(self);

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

# enum for the repeat of the habit
class Timing(enum.Enum):
    Hourly = 0
    Daily = 1
    Weekly = 2
    Monthly = 3
    
# establishes the connection to the database

mongo_client = MongoClient(os.environ['CONNECTION_STRING'], server_api=ServerApi('1'))
user_db = mongo_client["user-data"]
# Send a ping to confirm a successful connection
try:
    mongo_client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print(e)

# opens the discord client
intents = discord.Intents.default()
intents.message_content = True

client = HabotClient(intents=intents)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')


@client.tree.command()
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message('Pong!')
    
@client.tree.command()
@app_commands.describe(
    habit_name="The name of the habit",
    repeat="How often to do the habit",
                       )
async def add_habit(interaction: discord.Interaction, habit_name: str, repeat: Timing):
    user = interaction.user
    
    # Add habit to the database.
    habit_collection = user_db["habits"]

    habit = {
        "name": habit_name,
        "repeat": repeat.value,
        "user_id": user.id,
        "check_ins": []
    }
    try:
        habit_collection.insert_one(habit)
        await interaction.response.send_message(f"Added habit {habit_name} with repeat {repeat.name}")
    except Exception as e:
        print(e)
        await interaction.response.send_message(f"Error: Couldn't add habit to the database.")


@client.tree.command()
async def list_habits(interaction: discord.Interaction):
    user = interaction.user
    habit_collection = user_db["habits"]

    try:
        habits = habit_collection.find({"user_id": user.id})
        habits_list = list(habits)
        if len(habits_list) == 0:
            await interaction.response.send_message("You have no habits.")
            return
        else:
            joined_habits = ", ".join([f"\"{habit['name']}\", repeating {Timing(habit['repeat']).name}\n" for habit in habits_list])

            await interaction.response.send_message(f"Your habits are: \n{joined_habits}")
    except Exception as e:
        print(e)
        await interaction.response.send_message(f"Error: Couldn't list habits from the database.")

async def check_in(interaction: discord.Interaction, habit_name: str):
    user = interaction.user

    habit_collection = user_db["habits"]

    try:
        habit = habit_collection.find_one({"name": habit_name, "user_id": user.id})
        if habit is None:
            await interaction.response.send_message(f"You are not doing {habit_name}.")
        else:
            # has already checked in for the repeat cycle

            await interaction.response.send_message(f"Successfully checked in for {habit_name}.")

            
    except Exception as e:
        print(e)
        await interaction.response.send_message(f"Error: Couldn't check in.")

@client.tree.command()
@app_commands.describe(
    habit_name="The name of the habit",
)
async def remove_habit(interaction: discord.Interaction, habit_name: str):
    user = interaction.user
    habit_collection = user_db["habits"]

    try:
        habit_collection.delete_one({"name": habit_name, "user_id": user.id})
        await interaction.response.send_message(f"Removed habit {habit_name}")
    except Exception as e:
        print(e)
        await interaction.response.send_message(f"Error: Couldn't remove habit from the database.")

    
client.run(os.environ['DISCORD_TOKEN'])
