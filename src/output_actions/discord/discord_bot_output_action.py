import discord
import asyncio
import logging
import threading
from discord.ext import commands
from typing import Optional, Dict, Any

# Ensure src is in path for sibling imports
import sys
from pathlib import Path
SRC_DIR = Path(__file__).resolve().parent.parent.parent # Go up three levels: discord -> output_actions -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_output_action_secrets

# Set up logging
logger = logging.getLogger(__name__)

# Create a semaphore to ensure only one Discord bot operates at a time
discord_semaphore = threading.Semaphore(1)

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
        logger.warning(f"Attempted to send message to a null channel. Content: {content[:50]}...")
        return
    if not content:
        logger.warning("Attempted to send empty content.")
        return

    try:
        if len(content) <= max_length:
            await channel.send(content)
        else:
            # Split long messages into chunks
            for i in range(0, len(content), max_length):
                chunk = content[i:i + max_length]
                await channel.send(chunk)
                await asyncio.sleep(0.5)  # Brief pause between chunks to prevent rate limiting
    except discord.Forbidden:
        logger.error(f"Bot lacks permissions to send messages in channel {getattr(channel, 'id', 'unknown')}")
    except discord.HTTPException as e:
        logger.error(f"Failed to send message: {e}")
    except Exception as e:
        logger.error(f"Unexpected error during message sending: {e}", exc_info=True)


def process_output_action(agent_name: str, chat_model_response: str, meta_data: dict) -> None:
    """
    Processes the output from a chat model and sends it to a Discord channel using metadata.

    This function initializes a Discord bot from `meta_data`, retrieves the channel, and sends the message.
    A semaphore ensures only one instance of this function can access Discord at a time.

    :param agent_name: The agent's name generating the output.
    :param chat_model_response: The response from the chat model.
    :param meta_data: Metadata dictionary that must include:
                      - "channel_id": Discord channel to send the message to.
                      The bot token is retrieved from the agent's output action secrets.
    """
    # Acquire the semaphore to ensure only one Discord bot operates at a time
    with discord_semaphore:
        _process_discord_output(agent_name, chat_model_response, meta_data)

def _process_discord_output(agent_name: str, chat_model_response: str, meta_data: dict) -> None:
    """
    Internal function that handles the actual Discord bot operation.
    This is protected by a semaphore in the calling function.
    """
    channel_id = meta_data.get("channel_id")

    output_action_secrets = get_output_action_secrets(agent_name)

    token = output_action_secrets["secrets"].get("discord_bot_token")

    if channel_id is None:
        logger.error(f"'channel_id' missing from meta_data for agent '{agent_name}'.")
        return
        
    if token is None:
        logger.error(f"'discord_bot_token' missing from secrets for agent '{agent_name}'.")
        return
        
    try:
        channel_id = int(channel_id)
    except (ValueError, TypeError):
        logger.error(f"'channel_id' must be an integer, got '{channel_id}' for agent '{agent_name}'.")
        return

    # Set up necessary intents for the bot
    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True  # Required for message content access in newer Discord API

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready():
        logger.info(f"Bot connected as {bot.user.name} (ID: {bot.user.id}) for agent '{agent_name}'")
        channel = bot.get_channel(channel_id)
        if channel is None:
            logger.error(f"Channel with ID {channel_id} not found.")
        else:
            logger.info(f"Sending message to channel '{channel.name}' (ID: {channel_id})")
            ack_message_id = meta_data.get("ack_message_id")
            
            if ack_message_id:
                try:
                    # Ensure ack_message_id is an integer
                    ack_message_id = int(ack_message_id)
                    ack_message = await channel.fetch_message(ack_message_id)
                    if ack_message:
                        await ack_message.delete()
                        del meta_data["ack_message_id"]
                        logger.info(f"Deleted acknowledgment message {ack_message_id}")
                except ValueError:
                    logger.error(f"'ack_message_id' must be an integer, got '{ack_message_id}'")
                except discord.NotFound:
                    logger.error(f"ACK message with ID {ack_message_id} not found in channel {channel_id}")
                except discord.Forbidden:
                    logger.error(f"Bot lacks permissions to delete message {ack_message_id} in channel {channel_id}")
                except Exception as e:
                    logger.error(f"Error deleting ACK message: {e}", exc_info=True)

            await send_message(channel, chat_model_response)
            logger.info(f"Message sent to channel {channel_id} successfully")
        await bot.close()  # Disconnect after sending message

    # Run bot in a new event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        logger.info(f"Starting Discord bot for agent '{agent_name}' to send message to channel {channel_id}")
        loop.run_until_complete(bot.start(token))
    except discord.LoginFailure:
        logger.error(f"Failed to login with the provided token for agent '{agent_name}'.")
    except asyncio.TimeoutError:
        logger.error(f"Connection to Discord timed out for agent '{agent_name}'.")
    except Exception as e:
        logger.error(f"Unexpected error during bot execution for agent '{agent_name}': {e}", exc_info=True)
    finally:
        loop.close()
