# This example requires the 'message_content' intent.
from datetime import datetime, timedelta
import enum
import os
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands, tasks
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi


# loads environment variables from file
load_dotenv()

# sets the GUILD_ID environment variable for the testing server
MY_GUILD = discord.Object(id=os.environ['GUILD_ID'])

# client wrapper class for the habot client of the discord.py Client
class HabotClient(discord.Client):
    def __init__(self, intents: discord.Intents, client: MongoClient):
        super().__init__(intents=intents)

        self.db = client['user-data']

        self.tree = app_commands.CommandTree(self);

    def on_ready(self):
        print(f'We have logged in as {self.user}')
    
    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

        self.check_habits.start()

    @tasks.loop(minutes=1)
    async def check_habits(self):
        print("Checking habits...")
        
        # get all the habits
        all_habits = list(self.db['habits'].find())

        for habit in all_habits:
            if not datetime.now() > habit['due_date']:
               continue 
            
            # see if there is a check in within the habit's repeat cycle
            
            if not habit['has_checked_in']:
                print(habit['channel_id'])
                channel = self.get_channel(int(habit['channel_id']))
                user = self.get_user(int(habit['user_id']))
                await channel.send(f"Shame {user.mention} for not doing {habit['name']}.")

            # update due date

            new_date = Timing(habit['repeat']).next_timing(habit['due_date'])
            self.db['habits'].update_one({"name": habit['name'], "user_id": habit['user_id']}, {"$set": {"due_date": new_date, "has_checked_in": False}})


    @check_habits.before_loop
    async def before_my_task(self):
        await self.wait_until_ready() 

# enum for the repeat of the habit
class Timing(enum.Enum):
    Minutely = 0
    Hourly = 1
    Daily = 2
    Weekly = 3
    Monthly = 4

    def next_timing(self, current_time: datetime):
        match self:
            case Timing.Minutely:
                return current_time + timedelta(minutes=1)
            case Timing.Hourly:
                return current_time + timedelta(hours=1)
            case Timing.Daily:
                return current_time + timedelta(days=1)
            case Timing.Weekly:
                return current_time + timedelta(weeks=1)
            case Timing.Monthly:
                return current_time + timedelta(months=1)
    
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
intents.members = True

client = HabotClient(intents=intents, client=mongo_client)

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
        "channel_id": interaction.channel.id,
        "has_checked_in": False,
        "check_ins": [],
        "due_date": repeat.next_timing(datetime.now()),
        "created_at": interaction.created_at,
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

@client.tree.command()
@app_commands.describe(
    habit_name="The name of the habit",
)
async def check_in(interaction: discord.Interaction, habit_name: str):
    user = interaction.user

    habit_collection = user_db["habits"]

    try:
        habit = habit_collection.find_one({"name": habit_name, "user_id": user.id})
        if habit is None:
            await interaction.response.send_message(f"You are not doing {habit_name}.")
        else:
            # has already checked in for the repeat cycle
            if habit["has_checked_in"]:
                await interaction.response.send_message(f"You have already checked in for {habit_name}.")
                
            else:
                habit_collection.update_one({"name": habit_name, "user_id": user.id}, {"$set": {
                    "check_ins": habit["check_ins"] + [datetime.now()],
                    "has_checked_in": True
                }})

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
