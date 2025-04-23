import discord
import asyncio
from discord.ext import commands

DEFAULT_OUTPUT_NAME = "DiscordOutput"

def get_name() -> str:
    """
    Returns the name identifier for the Discord output handler.

    :return: The output handler name.
    """
    return DEFAULT_OUTPUT_NAME


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


async def delete_message(message: discord.Message) -> None:
    """
    Deletes a Discord message.

    :param message: The Discord message to delete.
    """
    if not message:
        return
    try:
        await message.delete()
    except discord.Forbidden:
        print(f"Error: Bot lacks permissions to delete message {message.id} in channel {message.channel.id}")
    except discord.NotFound:
        print(f"Warning: Message {message.id} not found (might have been already deleted).")
    except discord.HTTPException as e:
        print(f"Error: Failed to delete message {message.id}: {e}")


def process_output_action(agent_name: str, chat_model_response: str) -> None:
    """
    Placeholder for processing output from a chat model.

    :param agent_name: The agent's name generating the output.
    :param chat_model_response: The response from the chat model.
    """
    pass
