# src/input_triggers/discord/discord_bot_trigger.py
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

class DiscordBotTrigger(InputTrigger):
    """
    An input trigger that connects to Discord as a bot, listens for messages,
    and processes commands or mentions using an AI agent.
    """

    def __init__(self,
                 agent_name: str,
                 trigger_config_data: Optional[Dict[str, Any]] = None,
                 trigger_secrets: Optional[Dict[str, Any]] = None):
        """
        Initializes the DiscordBotTrigger.

        Args:
            agent_name: The name of the agent this trigger instance belongs to.
            trigger_config_data: Dictionary containing configuration for this trigger.
                                 Expected keys: None currently, but could include things like
                                 allowed_channels, command_prefix, etc.
            trigger_secrets: Dictionary containing secrets for this trigger.
                             Expected keys:
                             - 'discord_bot_token': The authentication token for the Discord bot.
        """
        super().__init__(agent_name, trigger_config_data, trigger_secrets)
        self.logger = logging.getLogger(f"{self.agent_name}.{self.name}") # Use specific logger

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

        self.logger.info(f"Discord Bot Trigger initialized for Agent '{self.agent_name}'")

    @property
    def name(self) -> str:
        return "DiscordBotTrigger"

    def _register_event_handlers(self):
        """Registers handlers for Discord client events."""
        @self.client.event
        async def on_ready():
            self.logger.info(f'Logged in as {self.client.user.name} (ID: {self.client.user.id})')
            self.logger.info('------ Discord Bot Ready ------')
            self._is_running = True

        @self.client.event
        async def on_message(message: discord.Message):
            # Ignore messages from the bot itself
            if message.author == self.client.user:
                return

            # Ignore messages from other bots (optional)
            if message.author.bot:
                 return

            self.logger.debug(f"Received message in #{message.channel} from {message.author}: {message.content}")

            # --- AI Agent Interaction Logic ---
            # Example: Process message if bot is mentioned or it's a DM
            is_mentioned = self.client.user in message.mentions
            is_dm = isinstance(message.channel, discord.DMChannel)

            if is_mentioned or is_dm:
                content_to_process = message.content
                if is_mentioned:
                    # Remove the mention from the content
                    content_to_process = content_to_process.replace(f'<@{self.client.user.id}>', '').strip()
                    self.logger.info(f"Bot mentioned by {message.author}. Processing: '{content_to_process}'")
                else:
                    self.logger.info(f"Received DM from {message.author}. Processing: '{content_to_process}'")


                # Define the callback for the AI response
                async def discord_callback(ai_response: str):
                    self.logger.info(f"Sending AI response back to Discord channel #{message.channel}")
                    try:
                        # Handle potential length limits (Discord limit is 2000 characters)
                        if len(ai_response) > 2000:
                             self.logger.warning("AI response exceeds 2000 characters. Truncating.")
                             # Consider splitting the message instead of truncating
                             await message.channel.send(ai_response[:2000])
                        else:
                             await message.channel.send(ai_response)
                    except discord.errors.Forbidden:
                        self.logger.error(f"Missing permissions to send message in channel #{message.channel}")
                    except Exception as e:
                        self.logger.error(f"Error sending AI response to Discord: {e}", exc_info=True)

                # Use the base class method to interact with the AI agent
                # Wrap the async discord_callback in a way that _execute_ai_agent_async can call it
                # Since _execute_ai_agent_async expects a synchronous callback, we need a bridge
                # or adjust _execute_ai_agent_async if it can handle awaitable callbacks.

                # Assuming _execute_ai_agent_async expects a sync callback for now:
                # We'll run the async callback in the bot's event loop.
                def sync_callback_wrapper(ai_response: str):
                    self.logger.debug("Sync wrapper called. Scheduling async Discord callback.")
                    asyncio.run_coroutine_threadsafe(discord_callback(ai_response), self.client.loop)

                # Start typing indicator
                async with message.channel.typing():
                    self._execute_ai_agent_async(
                        initial_query=content_to_process,
                        callback=sync_callback_wrapper # Pass the sync wrapper
                    )

            # --- Optional: MCP Command Check (if not handled by AI agent) ---
            # If you want the trigger to directly check for MCP commands *before*
            # sending to the AI, you could add:
            # elif self.contains_command(message.content):
            #     self.logger.info(f"Detected MCP command in message: {message.content}")
            #     # command_to_run = ... # Extract the specific command
            #     # result = self._run_mcp_command(command_to_run)
            #     # await message.channel.send(f"MCP Command Result:\n```\n{result}\n```")
            # else:
            #     # Message is not a mention, DM, or known command - ignore or log
            #     self.logger.debug("Ignoring message (not mention, DM, or command).")
            #     pass


        @self.client.event
        async def on_error(event, *args, **kwargs):
            self.logger.error(f"Unhandled error in Discord event '{event}':", exc_info=True)

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
        """Initializes the trigger (connects the bot)."""
        # Base class initialize gets the loop and logs
        await super().initialize()
        self.logger.info("Initializing Discord Bot Trigger...")

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

        self.logger.info("Starting Discord bot connection...")
        try:
            # Start the client. Runs until client.close() is called.
            # discord.py manages its own loop internally when run this way.
            # We run it in a separate task to not block the main async flow.
            self.logger.debug("Creating client.start task...")
            # Pass the token directly to start()
            self._connection_task = asyncio.create_task(self.client.start(self.bot_token), name=f"discord_bot_{self.agent_name}")
            self.logger.info("Discord client.start task created.")
            # Give it a moment to try and connect
            await asyncio.sleep(1)
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
        self.logger.info("Stopping Discord bot...")
        self._is_running = False # Mark as not running

        if self.client and self.client.is_ready():
            try:
                self.logger.info("Closing Discord client connection...")
                await self.client.close()
                self.logger.info("Discord client closed.")
            except Exception as e:
                self.logger.error(f"Error closing Discord client: {e}", exc_info=True)
        else:
             self.logger.info("Discord client was not running or already closed.")

        if self._connection_task and not self._connection_task.done():
             self.logger.info("Cancelling Discord connection task...")
             self._connection_task.cancel()
             try:
                 # Wait briefly for cancellation to be processed
                 await asyncio.wait_for(self._connection_task, timeout=5.0)
             except asyncio.CancelledError:
                 self.logger.info("Discord connection task cancelled successfully.")
             except asyncio.TimeoutError:
                 self.logger.warning("Timeout waiting for Discord connection task to cancel.")
             except Exception as e:
                  # Log errors that might occur during cancellation itself
                  self.logger.error(f"Error during Discord task cancellation: {e}", exc_info=True)
        self._connection_task = None # Clear the task reference

        self.logger.info("DiscordBotTrigger stopped.")

