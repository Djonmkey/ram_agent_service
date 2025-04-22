# src/input_triggers/discord/discord_bot_trigger.py
import json
import asyncio
import discord
import logging
from typing import Optional, Dict, Any

# Ensure src is in path for sibling imports
import sys
from pathlib import Path
SRC_DIR = Path(__file__).resolve().parent.parent.parent # Go up three levels: discord -> input_triggers -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from input_triggers.input_triggers import InputTrigger
from ras import work_queue_manager

class DiscordBotTrigger(InputTrigger):
    """
    An input trigger that connects to Discord as a bot, listens for messages,
    and processes commands or mentions using an AI agent.
    """

    def __init__(self,
                 agent_config_data: Dict[str, Any],
                 trigger_config_data: Optional[Dict[str, Any]] = None,
                 trigger_secrets: Optional[Dict[str, Any]] = None):
        """
        Initializes the DiscordBotTrigger.

        Args:
            agent_config_data: Dictionary containing the configuration for the agent
                               this trigger belongs to (includes agent name).
            trigger_config_data: Dictionary containing configuration for this trigger.
                                 Expected keys: None currently, but could include things like
                                 allowed_channels, command_prefix, etc.
            trigger_secrets: Dictionary containing secrets for this trigger.
                             Expected keys:
                             - 'discord_bot_token': The authentication token for the Discord bot.
        """
        # Changed: Pass the full agent_config_data to the base class
        super().__init__(agent_config_data, trigger_config_data, trigger_secrets)
        # self.agent_name is now set by the base class __init__

        # Use the logger initialized by the base class or re-initialize if needed
        # The base class already initializes self.logger correctly like this:
        # self.logger = logging.getLogger(f"{self.agent_name}.{self.__class__.__name__}")
        # So, no need to redefine self.logger here unless you want a different format.

        # --- Configuration & Secrets ---
        # Get the bot token from the secrets passed during initialization
        self.bot_token = self.trigger_secrets.get("discord_bot_token")
        if not self.bot_token:
            # Log an error and potentially raise an exception if the token is essential
            self.logger.error("Discord bot token ('discord_bot_token') not found in trigger secrets!")
            # Depending on requirements, you might want to raise an error here:
            # raise ValueError("Discord bot token is missing.")
        else:
             self.logger.info("Discord bot token loaded.")
             # Avoid logging the token itself for security

        # --- Discord Client Setup ---
        intents = discord.Intents.default()
        intents.messages = True  # Need permission to read messages
        intents.message_content = True # Need permission to read message content (Privileged Intent)
        self.client = discord.Client(intents=intents)

        # --- Internal State ---
        self._is_running = False
        self._connection_task = None

        # --- Event Handlers ---
        self._register_event_handlers()

        # Use self.agent_name which is set by the base class
        self.logger.info(f"Discord Bot Trigger initialized for Agent '{self.agent_name}'")

    @property
    def name(self) -> str:
        return "DiscordBotTrigger"

    async def send_long_message(self, message_content: str, channel, max_length: int = 2000) -> None:
        """
        Sends a message to a Discord channel, splitting it into chunks if it exceeds max_length.

        :param message_content: The full string content to send.
        :param channel: The Discord channel to send the message to.
        :param max_length: The maximum length of a single Discord message (default is 2000).
        """
        if len(message_content) <= max_length:
            await channel.send(message_content)
        else:
            for i in range(0, len(message_content), max_length):
                chunk = message_content[i:i + max_length]
                await channel.send(chunk)
                await asyncio.sleep(1)
                
    def _register_event_handlers(self):
        """Registers handlers for Discord client events."""
        @self.client.event
        async def on_ready():
            self.logger.info(f'Logged in as {self.client.user.name} (ID: {self.client.user.id})')
            self.logger.info('------ Discord Bot Ready ------')
            self._is_running = True

        @self.client.event
        async def on_message(message: discord.Message):
            """
            Respond to simple messages and pass commands for processing.

            :param message: Message received from Discord.
            """
            if message.author == self.client.user:
                return

            # Immediately respond to prevent timeout
            ack_message = await message.channel.send("Working on it...")

            input_trigger_content = {
                "content": message.content,
                "timestamp": message.created_at.isoformat(),
                "meta_data": {
                    "message_id": message.id,
                    "ack_message_id": ack_message.id,
                    "channel_id": message.channel.id,
                    "guild_id": message.guild.id if message.guild else None,
                    "author_id": message.author.id,
                    "author_name": str(message.author)
                }
            }

            agent_name = self.agent_config_data["name"]

            work_queue_manager.enqueue_input_trigger(agent_name, input_trigger_content)
            
            """
            async def handle_long_task():
                response_future = asyncio.Future()

                async def set_response(result):
                    # Send the final response
                    if agent_response:
                        await self.send_long_message(agent_response, message.channel)
                    else:
                        await message.channel.send("Sorry, I couldn't generate a response.")

                # Queue the GPT request on a separate thread
                self._execute_ai_agent_async(message.content, set_response)

                # Await the result
                agent_response = await response_future

                # Delete the "working" message
                try:
                    await ack_message.delete()
                except discord.HTTPException:
                    pass  # Ignore if message already deleted or not found

                # Send the final response
                if agent_response:
                    await self.send_long_message(agent_response, message.channel)
                else:
                    await message.channel.send("Sorry, I couldn't generate a response.")

            # Run the long task in the background
            asyncio.create_task(handle_long_task())
            """


        @self.client.event
        async def on_error(event, *args, **kwargs):
            self.logger.error(f"Unhandled error in Discord event '{event}':", exc_info=True)
            # Attempt to log more details if available
            if args:
                self.logger.error(f"Event args: {args}")
            if kwargs:
                self.logger.error(f"Event kwargs: {kwargs}")


        @self.client.event
        async def on_disconnect():
            self.logger.warning("Discord client disconnected.")
            self._is_running = False
            # Optional: Implement reconnection logic here if needed

        @self.client.event
        async def on_resumed():
            self.logger.info("Discord client reconnected and resumed.")
            self._is_running = True


    async def initialize(self):
        """Initializes the trigger (checks token)."""
        # Base class initialize gets the loop and logs
        await super().initialize()
        # Use self.agent_name set by base class
        self.logger.info(f"Initializing Discord Bot Trigger for Agent '{self.agent_name}'...")

        if not self.bot_token:
             self.logger.error("Cannot initialize Discord bot: Token is missing.")
             raise ValueError("Discord bot token is required but was not provided in secrets.")

        # Initialization primarily involves ensuring the token is present.
        # The actual connection happens in start().
        self.logger.info("Discord Bot Trigger initialized (token present).")


    async def start(self):
        """Starts the Discord bot and connects to Discord."""
        await super().start() # Log start message

        if not self.bot_token:
            self.logger.error("Cannot start Discord bot: Token is missing.")
            return # Or raise an error

        if self._connection_task and not self._connection_task.done():
             self.logger.warning("Bot connection task already running.")
             return

        # Use self.agent_name set by base class
        self.logger.info(f"Starting Discord bot connection for Agent '{self.agent_name}'...")
        try:
            # Start the client. Runs until client.close() is called.
            # discord.py manages its own loop internally when run this way.
            # We run it in a separate task to not block the main async flow.
            self.logger.debug("Creating client.start task...")
            # Pass the token directly to start()
            # Use agent_name in task name for clarity if multiple discord bots run
            self._connection_task = asyncio.create_task(
                self.client.start(self.bot_token),
                name=f"discord_bot_{self.agent_name}"
            )
            self.logger.info(f"Discord client.start task created (Task Name: {self._connection_task.get_name()}).")
            # Give it a moment to try and connect
            await asyncio.sleep(5) # Slightly longer sleep
            if not self.client.is_ready():
                 self.logger.warning("Discord client may still be connecting...")
            # The task now runs in the background.

        except discord.LoginFailure:
            self.logger.error("Failed to log in to Discord: Invalid token.")
            self._is_running = False
            # Re-raise or handle appropriately
            raise
        except Exception as e:
            self.logger.error(f"Error starting Discord bot: {e}", exc_info=True)
            self._is_running = False
            # Re-raise or handle appropriately
            raise

    async def stop(self):
        """Stops the Discord bot and disconnects."""
        await super().stop() # Log stop message
        # Use self.agent_name set by base class
        self.logger.info(f"Stopping Discord bot for Agent '{self.agent_name}'...")
        self._is_running = False # Mark as not running

        # Check if client exists and is connected before trying to close
        if hasattr(self, 'client') and self.client and not self.client.is_closed():
            try:
                self.logger.info("Closing Discord client connection...")
                await self.client.close()
                self.logger.info("Discord client closed.")
            except Exception as e:
                self.logger.error(f"Error closing Discord client: {e}", exc_info=True)
        else:
             self.logger.info("Discord client was not running or already closed.")

        if self._connection_task and not self._connection_task.done():
             task_name = self._connection_task.get_name()
             self.logger.info(f"Cancelling Discord connection task ('{task_name}')...")
             self._connection_task.cancel()
             try:
                 # Wait briefly for cancellation to be processed
                 await asyncio.wait_for(self._connection_task, timeout=5.0)
             except asyncio.CancelledError:
                 self.logger.info(f"Discord connection task ('{task_name}') cancelled successfully.")
             except asyncio.TimeoutError:
                 self.logger.warning(f"Timeout waiting for Discord connection task ('{task_name}') to cancel.")
             except Exception as e:
                  # Log errors that might occur during cancellation itself
                  self.logger.error(f"Error during Discord task ('{task_name}') cancellation: {e}", exc_info=True)
        self._connection_task = None # Clear the task reference

        self.logger.info(f"DiscordBotTrigger stopped for Agent '{self.agent_name}'.")

