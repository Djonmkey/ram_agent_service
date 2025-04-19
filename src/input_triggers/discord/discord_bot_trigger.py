# src/input_triggers/discord/discord_bot_trigger.py
import json
import os
import discord
import sys
import asyncio
from discord.ext import commands

# Add project root to path to allow sibling imports (e.g., output_actions)
# Adjust depth as necessary based on your execution context
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.append(PROJECT_ROOT)

from src.gpt_thread import get_gpt_handler # Assuming gpt_thread is in src
from src.event_listener import EventListener # Assuming event_listener is in src
# Import the new output action class
from src.output_actions.discord.discord_bot_output_action import DiscordBotOutputAction

class DiscordEventListener(EventListener):
    """
    Discord implementation of EventListener interface.
    Focuses on receiving messages and triggering actions.
    """

    def __init__(self, config_path: str = None):
        """
        Initialize Discord event listener.

        Args:
            config_path: Path to the configuration JSON file. If None, uses default path.
        """
        self._name = "DiscordTrigger"
        # Consider making the config file name match the trigger file name
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), 'discord_bot_trigger.json')
        self.bot: commands.Bot = None
        self.token: str = None
        self.task: asyncio.Task = None
        self.loop: asyncio.AbstractEventLoop = None
        self.output_action: DiscordBotOutputAction = None # Placeholder for the output handler

    @property
    def name(self) -> str:
        """Get the name of the event listener."""
        return self._name

    # Removed send_long_message - moved to DiscordBotOutputAction

    async def initialize(self):
        """Initialize the Discord bot and the associated output action handler."""
        self.token = self._load_discord_token()
        if not self.token:
             print("Error: Discord token could not be loaded. Cannot initialize.")
             return # Or raise an exception

        self.loop = asyncio.get_running_loop()

        intents = discord.Intents.default()
        intents.message_content = True # Ensure this is enabled in Discord Developer Portal

        self.bot = commands.Bot(command_prefix='!', intents=intents)

        # Initialize the output action handler, passing the bot instance
        self.output_action = DiscordBotOutputAction(self.bot)

        # --- Register Event Handlers ---
        self._register_event_handlers()


    def _register_event_handlers(self):
        """Registers discord.py event handlers."""

        @self.bot.event
        async def on_ready():
            print(f'Discord Trigger: Logged in as {self.bot.user}')
            print(f'Discord Output Action: Initialized for bot {self.output_action.bot.user}')

        @self.bot.event
        async def on_message(message: discord.Message):
            """Handle incoming messages."""
            if message.author == self.bot.user:
                return # Ignore messages from the bot itself

            # --- Acknowledge Receipt (Optional but Recommended) ---
            # Sending the ack message is technically output, but tightly coupled to input processing start.
            # Alternatively, the output_action could have an acknowledge method.
            ack_message = None
            try:
                # Send ack immediately
                ack_message = await message.channel.send("Working on it...")
            except discord.Forbidden:
                 print(f"Warning: Cannot send ack message in channel {message.channel.id} (missing permissions).")
            except discord.HTTPException as e:
                 print(f"Warning: Failed to send ack message in channel {message.channel.id}: {e}")


            # --- Process the message asynchronously ---
            async def handle_long_task():
                response_future = asyncio.Future()

                # Callback for the AI agent thread to set the result in the main loop
                def set_response(result):
                    if self.loop and not self.loop.is_closed():
                        self.loop.call_soon_threadsafe(response_future.set_result, result)
                    else:
                         # Handle case where loop is closed before response arrives
                         print("Warning: Event loop closed before AI response could be processed.")
                         # Attempt to set result anyway, might fail silently or raise
                         try:
                            response_future.set_result(None) # Indicate failure or no result
                         except Exception:
                            pass


                # Queue the GPT request on a separate thread
                # Pass the callback to bridge the thread and asyncio event loop
                self._execute_ai_agent_async(message.content, set_response)

                # Await the result from the AI agent thread
                agent_response = await response_future

                # --- Clean up Ack Message ---
                if ack_message:
                    await self.output_action.delete_message(ack_message) # Use output action to delete

                # --- Send Final Response via Output Action ---
                if agent_response:
                    await self.output_action.send_message(message.channel, agent_response)
                else:
                    # Handle cases where the agent explicitly returned nothing or an error occurred
                    await self.output_action.send_message(message.channel, "Sorry, I couldn't generate a response.")

            # Run the processing task without blocking the on_message handler
            asyncio.create_task(handle_long_task())


        @self.bot.command(name='agent')
        async def run_agent(ctx: commands.Context, *, query: str):
            """Handle the !agent command."""
            # Create a Future to await the response from the AI agent thread
            response_future = asyncio.Future()

            # Callback for the AI agent thread
            def set_response(result):
                 if self.loop and not self.loop.is_closed():
                    self.loop.call_soon_threadsafe(response_future.set_result, result)
                 else:
                    print("Warning: Event loop closed before AI response could be processed for !agent command.")
                    try:
                        response_future.set_result(None)
                    except Exception:
                        pass

            # Send typing indicator while waiting
            async with ctx.typing():
                # Queue the GPT request on a separate thread
                self._execute_ai_agent_async(query, set_response)

                # Wait for the response from the AI agent
                response = await response_future

                # --- Send Response via Output Action ---
                if response:
                    await self.output_action.send_reply(ctx, response) # Use send_reply for context
                else:
                    await self.output_action.send_reply(ctx, "Sorry, there was an issue generating the response for your command.")


    async def start(self):
        """Start the Discord bot event listener."""
        if not self.bot or not self.token or not self.output_action:
            print("Trigger not initialized. Call initialize() first.")
            await self.initialize() # Attempt initialization
            # Check again after attempting initialization
            if not self.bot or not self.token or not self.output_action:
                 print("Initialization failed. Cannot start trigger.")
                 return None # Indicate failure to start

        if self.task and not self.task.done():
            print("Trigger task is already running.")
            return self.task

        print("Starting Discord trigger...")
        # Run the bot's main loop
        # Note: bot.start() is blocking, so we run it in a task
        # to allow the main application to continue (if applicable)
        self.task = asyncio.create_task(self.bot.start(self.token))
        print("Discord trigger task created.")
        return self.task # Return the task so it can be awaited or managed

    async def stop(self):
        """Stop the Discord bot gracefully."""
        print("Stopping Discord trigger...")
        if self.bot and not self.bot.is_closed():
            await self.bot.close()
            print("Discord bot connection closed.")

        if self.task:
            if not self.task.done():
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    print("Discord trigger task cancelled successfully.")
                except Exception as e:
                    print(f"Error during trigger task cancellation: {e}")
            else:
                 # Check for exceptions if the task finished unexpectedly
                 if self.task.exception():
                      print(f"Discord trigger task finished with exception: {self.task.exception()}")
                 else:
                      print("Discord trigger task already finished.")
        self.task = None
        print("Discord trigger stopped.")


    def _load_discord_token(self) -> str | None:
        """
        Load the Discord bot token from the JSON configuration file.

        Returns:
            Discord bot token string, or None if loading fails.
        """
        if not os.path.exists(self.config_path):
            print(f"Error: Config file not found: {self.config_path}")
            return None

        try:
            with open(self.config_path, 'r') as f:
                config = json.load(f)

            token = config.get('discord_bot_token') # Use .get for safer access
            if not token:
                print(f"Error: 'discord_bot_token' missing or empty in config file: {self.config_path}")
                return None
            return token
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from config file: {self.config_path}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred loading the token: {e}")
            return None


    def _execute_ai_agent_async(self, query: str, callback) -> None:
        """
        Executes the AI agent in a separate thread and uses a callback
        to return the result to the asyncio event loop.

        Args:
            query: Command or message from Discord.
            callback: A function (like set_response) to call with the result.
                      This callback must be thread-safe or scheduled correctly
                      (e.g., using loop.call_soon_threadsafe).
        """
        try:
            # Get the GPT handler (assuming it's thread-safe or creates new instances)
            gpt_handler = get_gpt_handler()

            # Run the potentially blocking call in the default executor (thread pool)
            self.loop.run_in_executor(
                None, # Use default executor
                self._blocking_ai_call, # The function to run
                gpt_handler, # Argument for the function
                query, # Argument for the function
                callback # Argument for the function
            )
        except Exception as e:
            print(f"Error submitting AI task to executor: {e}")
            # Immediately call back with an error indicator if submission fails
            callback(None) # Or pass a specific error message/object

    def _blocking_ai_call(self, gpt_handler, query, callback):
        """
        Synchronous wrapper for the AI call, intended to be run in a thread.
        Calls the provided callback with the result.
        """
        try:
            response = gpt_handler.ask_gpt_sync(query)
            callback(response)
        except Exception as e:
            print(f"Error during AI agent execution in background thread: {e}")
            callback(None) # Signal an error occurred


# --- Main execution block (for standalone testing) ---
if __name__ == '__main__':
    async def main():
        print("Initializing Discord Event Listener for standalone run...")
        listener = DiscordEventListener()
        # Initialization now also sets up the output_action
        await listener.initialize()

        if not listener.bot:
             print("Listener initialization failed. Exiting.")
             return

        # Start the listener (which starts the bot)
        listener_task = await listener.start()

        if not listener_task:
             print("Listener failed to start. Exiting.")
             return

        # Keep the main script alive until interrupted
        print("Discord bot trigger is running. Press Ctrl+C to exit.")
        try:
            # Wait for the listener task to complete (e.g., on bot disconnect or error)
            # or until KeyboardInterrupt
            await listener_task
        except KeyboardInterrupt:
            print("\nCtrl+C received. Shutting down...")
        except Exception as e:
             print(f"\nAn unexpected error occurred in the main loop: {e}")
        finally:
            print("Stopping listener...")
            await listener.stop()
            print("Shutdown complete.")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Main execution interrupted.")
