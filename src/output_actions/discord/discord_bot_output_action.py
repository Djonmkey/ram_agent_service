# src/output_actions/discord/discord_bot_output_action.py
import discord
import asyncio
from discord.ext import commands

class DiscordBotOutputAction:
    """Handles sending messages and replies via a Discord bot."""

    def __init__(self, bot: commands.Bot):
        """
        Initializes the output action handler.

        Args:
            bot: The initialized discord.ext.commands.Bot instance.
        """
        if not bot:
            raise ValueError("A valid discord.ext.commands.Bot instance is required.")
        self.bot = bot
        self._name = "DiscordOutput"

    @property
    def name(self) -> str:
        """Get the name of the output action handler."""
        return self._name

    async def send_message(self, channel: discord.abc.Messageable, content: str, max_length: int = 2000) -> None:
        """
        Sends a message to a specific Discord channel, handling potential length limits.

        Args:
            channel: The Discord channel (or any Messageable) to send the message to.
            content: The string content of the message.
            max_length: The maximum length for a single Discord message chunk.
        """
        if not channel:
            print(f"Warning: Attempted to send message to a null channel. Content: {content[:50]}...")
            return
        if not content:
            print(f"Warning: Attempted to send empty content to channel {channel.id}.")
            # Optionally send a placeholder or just return
            # await channel.send("Received empty response.")
            return

        try:
            if len(content) <= max_length:
                await channel.send(content)
            else:
                # Send long messages in chunks
                for i in range(0, len(content), max_length):
                    chunk = content[i:i + max_length]
                    await channel.send(chunk)
                    # Add a small delay to avoid rate limiting issues, especially for many chunks
                    await asyncio.sleep(0.5)
        except discord.Forbidden:
            print(f"Error: Bot lacks permissions to send messages in channel {channel.id}")
        except discord.HTTPException as e:
            print(f"Error: Failed to send message to channel {channel.id}: {e}")
        except Exception as e:
            # Catch other potential errors
            print(f"An unexpected error occurred during message sending to {channel.id}: {e}")

    async def send_reply(self, ctx: commands.Context, content: str, max_length: int = 2000) -> None:
        """
        Sends a reply within the context of a command, handling potential length limits.

        Args:
            ctx: The command context provided by discord.py.
            content: The string content of the reply.
            max_length: The maximum length for a single Discord message chunk.
        """
        # Commands context's channel attribute is Messageable
        await self.send_message(ctx.channel, content, max_length)

    async def delete_message(self, message: discord.Message) -> None:
        """
        Deletes a specific Discord message.

        Args:
            message: The discord.Message object to delete.
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

