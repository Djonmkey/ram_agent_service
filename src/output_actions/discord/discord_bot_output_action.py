import discord
import asyncio
from discord.ext import commands
from typing import Optional

# Ensure src is in path for sibling imports
import sys
from pathlib import Path
SRC_DIR = Path(__file__).resolve().parent.parent.parent # Go up three levels: discord -> input_triggers -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_output_action_secrets

async def send_message(
    channel: discord.abc.Messageable,
    content: str,
    max_length: int = 2000
) -> None:
    """
    Sends a message to a specific Discord channel, handling Discord's message length limits.

    :param channel: The Discord channel or Messageable to send the message to.
    :param content: The message content.
    :param max_length: The maximum character length per message (default is 2000).
    """
    if not channel:
        print(f"Warning: Attempted to send message to a null channel. Content: {content[:50]}...")
        return
    if not content:
        print("Warning: Attempted to send empty content.")
        return

    try:
        if len(content) <= max_length:
            await channel.send(content)
        else:
            for i in range(0, len(content), max_length):
                chunk = content[i:i + max_length]
                await channel.send(chunk)
                await asyncio.sleep(0.5)
    except discord.Forbidden:
        print(f"Error: Bot lacks permissions to send messages in channel {getattr(channel, 'id', 'unknown')}")
    except discord.HTTPException as e:
        print(f"Error: Failed to send message: {e}")
    except Exception as e:
        print(f"Unexpected error during message sending: {e}")


def process_output_action(agent_name: str, chat_model_response: str, meta_data: dict) -> None:
    """
    Processes the output from a chat model and sends it to a Discord channel using metadata.

    This function initializes a Discord bot from `meta_data`, retrieves the channel, and sends the message.

    :param agent_name: The agent's name generating the output.
    :param chat_model_response: The response from the chat model.
    :param meta_data: Metadata dictionary that must include:
                      - "channel_id": Discord channel to send the message to.
                      - "bot_token": Token to initialize a new bot instance.
    """
    channel_id: Optional[int] = meta_data.get("channel_id")

    output_action_secrets = get_output_action_secrets(agent_name)

    token = output_action_secrets["secrets"].get("discord_bot_token")

    if channel_id is None or token is None:
        print("Error: 'channel_id' or 'bot_token' missing from meta_data.")
        return

    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        channel = bot.get_channel(channel_id)
        if channel is None:
            print(f"Error: Channel with ID {channel_id} not found.")
        else:
            await send_message(channel, chat_model_response)
        await bot.close()  # Disconnect after sending message

    # Run bot in a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.start(token))
    finally:
        loop.close()
