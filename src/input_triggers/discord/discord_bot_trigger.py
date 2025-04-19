# src/input_triggers/discord/discord_bot_trigger.py
import discord
import asyncio
import os
import sys
from discord.ext import commands
from typing import Optional

# Use Pathlib and ensure src is discoverable
from pathlib import Path
SRC_DIR = Path(__file__).resolve().parent.parent.parent # discord -> input_triggers -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import base class and output action
from input_triggers.input_triggers import InputTrigger
from output_actions.discord.discord_bot_output_action import DiscordBotOutputAction

# Default config path relative to this file
DEFAULT_CONFIG_PATH = Path(__file__).parent / "discord_bot_trigger.json"

class DiscordEventListener(InputTrigger):
    """
    Discord input trigger using discord.py.
    Listens for messages and commands, interacts with the AI agent via the base class.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Discord event listener.

        Args:
            config_path: Path to the configuration JSON file.
                         Defaults to discord_bot_trigger.json in the same directory.
        """
        # Initialize base class (loads config, sets up logger)
        super().__init__(config_path=config_path or str(DEFAULT_CONFIG_PATH))

        self.bot: Optional[commands.Bot] = None
        self.token: Optional[str] = None
        self.task: Optional[asyncio.Task] = None
        self.output_action: Optional[DiscordBotOutputAction] = None

    @property
    def name(self) -> str:
        """Get the name of the event listener."""
        return self.config.get("trigger_name", "DiscordTrigger") # Get name from config or default

    async def initialize(self):
        """Initialize the Discord bot and the associated output action handler."""
        await super().initialize() # Sets up self.loop

        self.token = self.config.get('discord_bot_token')
        if not self.token:
             self.logger.critical("Discord token ('discord_bot_token') not found in configuration. Cannot initialize.")
             raise ValueError("Discord token missing in configuration.")

        intents = discord.Intents.default()
        # Ensure message content intent is enabled in config and Discord Dev Portal
        if self.config.get("enable_message_content_intent", True):
             intents.message_content = True
             self.logger.info("Message content intent enabled.")
        else:
             self.logger.warning("Message content intent is disabled. Bot may not read message content.")

        command_prefix = self.config.get("command_prefix", "!")
        self.bot = commands.Bot(command_prefix=command_prefix, intents=intents)

        # Initialize the output action handler, passing the bot instance
        try:
            self.output_action = DiscordBotOutputAction(self.bot)
            self.logger.info("Discord Output Action initialized.")
        except Exception as e:
            self.logger.critical(f"Failed to initialize DiscordBotOutputAction: {e}", exc_info=True)
            raise # Re-raise critical error

        # Register event handlers
        self._register_event_handlers()
        self.logger.info(f"Discord trigger '{self.name}' initialized successfully.")


    def _register_event_handlers(self):
        """Registers discord.py event handlers."""
        if not self.bot or not self.output_action:
            self.logger.error("Bot or Output Action not initialized, cannot register handlers.")
            return

        @self.bot.event
        async def on_ready():
            self.logger.info(f'Discord Bot Logged in as {self.bot.user}')
            self.logger.info(f'Output Action ready for bot {self.output_action.bot.user}') # type: ignore

        @self.bot.event
        async def on_message(message: discord.Message):
            """Handle incoming messages."""
            if message.author == self.bot.user:
                return # Ignore messages from the bot itself
            if message.content.startswith(self.bot.command_prefix):
                 # Let the command handler process commands
                 await self.bot.process_commands(message)
                 return

            self.logger.info(f"Received message from {message.author} in #{message.channel}: {message.content[:50]}...")

            # --- Acknowledge Receipt (Optional but Recommended) ---
            ack_message = None
            if self.config.get("send_acknowledgement", True):
                try:
                    ack_message = await message.channel.send("Working on it...")
                    self.logger.debug(f"Sent acknowledgement to #{message.channel}")
                except discord.Forbidden:
                    self.logger.warning(f"Cannot send ack message in channel {message.channel.id} (missing permissions).")
                except discord.HTTPException as e:
                    self.logger.warning(f"Failed to send ack message in channel {message.channel.id}: {e}")

            # --- Define the callback for the AI agent ---
            async def final_callback(agent_response: str):
                self.logger.info(f"Received final AI response for message {message.id}. Length: {len(agent_response)}")
                # Clean up Ack Message
                if ack_message:
                    try:
                        await self.output_action.delete_message(ack_message) # type: ignore
                        self.logger.debug(f"Deleted acknowledgement message {ack_message.id}")
                    except Exception as e:
                        self.logger.warning(f"Failed to delete ack message {ack_message.id}: {e}")

                # Send Final Response via Output Action
                if agent_response:
                    await self.output_action.send_message(message.channel, agent_response) # type: ignore
                else:
                    # Handle cases where the agent explicitly returned nothing or an error occurred
                    self.logger.warning(f"AI agent returned empty or error response for message {message.id}")
                    await self.output_action.send_message(message.channel, "Sorry, I couldn't generate a response.") # type: ignore

            # --- Execute AI agent using base class method ---
            # Pass the original message content as the initial query
            # The callback defined above will handle the final result
            self._execute_ai_agent_async(message.content, final_callback)


        @self.bot.command(name=self.config.get("agent_command_name", "agent"))
        async def run_agent_command(ctx: commands.Context, *, query: str):
            """Handle the agent command."""
            self.logger.info(f"Received command '{ctx.command.name}' from {ctx.author} with query: {query[:50]}...")

            # --- Define the callback for the AI agent ---
            async def final_callback(agent_response: str):
                self.logger.info(f"Received final AI response for command {ctx.message.id}. Length: {len(agent_response)}")
                # Send Final Response via Output Action using reply context
                if agent_response:
                    await self.output_action.send_reply(ctx, agent_response) # type: ignore
                else:
                    self.logger.warning(f"AI agent returned empty or error response for command {ctx.message.id}")
                    await self.output_action.send_reply(ctx, "Sorry, there was an issue generating the response for your command.") # type: ignore

            # Send typing indicator while waiting
            async with ctx.typing():
                # --- Execute AI agent using base class method ---
                self._execute_ai_agent_async(query, final_callback)

        self.logger.debug("Discord event handlers registered.")


    async def start(self):
        """Start the Discord bot event listener."""
        await super().start() # Log start message

        if not self.bot or not self.token or not self.output_action:
            self.logger.error("Trigger not properly initialized. Call initialize() first and ensure token is valid.")
            # Optionally re-attempt initialization or raise error
            # await self.initialize()
            # if not self.bot or not self.token or not self.output_action:
            #      raise RuntimeError("Discord trigger initialization failed.")
            return # Or raise error

        if self.task and not self.task.done():
            self.logger.warning("Start called but trigger task is already running.")
            return self.task

        self.logger.info("Starting Discord bot connection...")
        try:
            # Run the bot's main loop in a task
            self.task = asyncio.create_task(self.bot.start(self.token), name=f"{self.name}_run")
            self.logger.info(f"Discord trigger task '{self.task.get_name()}' created.")
            # You might want to await self.bot.wait_until_ready() here if needed
            # await self.bot.wait_until_ready()
            # self.logger.info("Bot is ready.")
            return self.task
        except discord.LoginFailure:
            self.logger.critical("Login failed: Improper token provided.")
            raise
        except Exception as e:
            self.logger.critical(f"Failed to start Discord bot: {e}", exc_info=True)
            self.task = None # Ensure task is None if start fails
            raise # Re-raise the exception


    async def stop(self):
        """Stop the Discord bot gracefully."""
        await super().stop() # Log stop message

        if self.bot and not self.bot.is_closed():
            self.logger.info("Closing Discord bot connection...")
            await self.bot.close()
            self.logger.info("Discord bot connection closed.")

        if self.task:
            task_name = self.task.get_name()
            if not self.task.done():
                self.logger.info(f"Cancelling trigger task '{task_name}'...")
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    self.logger.info(f"Trigger task '{task_name}' cancelled successfully.")
                except Exception as e:
                    # Log exceptions that might occur during task cleanup
                    self.logger.error(f"Error during trigger task '{task_name}' cancellation/cleanup: {e}", exc_info=True)
            else:
                 # Check if the task finished with an exception
                 exception = self.task.exception()
                 if exception:
                      self.logger.error(f"Trigger task '{task_name}' finished with an exception: {exception}", exc_info=exception)
                 else:
                      self.logger.info(f"Trigger task '{task_name}' already finished.")
        self.task = None
        self.logger.info(f"Discord trigger '{self.name}' stopped.")

