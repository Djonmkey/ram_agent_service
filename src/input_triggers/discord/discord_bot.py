import json
import os
import discord
import sys
import asyncio
from discord.ext import commands

# Add parent directory to path to import from main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gpt_thread import get_gpt_handler
from event_listener import EventListener

class DiscordEventListener(EventListener):
    """Discord implementation of EventListener interface"""
    
    def __init__(self, config_path: str = None):
        """
        Initialize Discord event listener.
        
        Args:
            config_path: Path to the configuration JSON file. If None, uses default path.
        """
        self._name = "Discord"
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), 'discord_bot.json')
        self.bot = None
        self.token = None
        self.task = None
        self.loop = None  # Save the main asyncio loop
    
    @property
    def name(self) -> str:
        """Get the name of the event listener."""
        return self._name

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

    async def initialize(self):
        """Initialize the Discord bot."""
        self.token = self._load_discord_token()
        self.loop = asyncio.get_running_loop()

        intents = discord.Intents.default()
        intents.message_content = True
        
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        
        # Set up event handlers
        @self.bot.event
        async def on_ready():
            print(f'Logged in as {self.bot.user}')

        @self.bot.event
        async def on_message(message: discord.Message):
            """
            Respond to simple messages and pass commands for processing.

            :param message: Message received from Discord.
            """
            if message.author == self.bot.user:
                return

            # Immediately respond to prevent timeout
            ack_message = await message.channel.send("Working on it...")

            async def handle_long_task():
                response_future = asyncio.Future()

                def set_response(result):
                    if self.loop and not self.loop.is_closed():
                        self.loop.call_soon_threadsafe(response_future.set_result, result)

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


        @self.bot.command(name='agent')
        async def run_agent(ctx, *, query: str):
            """
            Handle the !agent command to run an AI agent query.

            :param ctx: Context of the command.
            :param query: Text following the command to process.
            """
            # Create a Future to get the response
            response_future = asyncio.Future()
            
            def set_response(result):
                if self.loop and not self.loop.is_closed():
                    self.loop.call_soon_threadsafe(response_future.set_result, result)
            
            # Send typing indicator while waiting
            async with ctx.typing():
                # Queue the GPT request on a separate thread
                self._execute_ai_agent_async(query, set_response)
                
                # Wait for the response
                response = await response_future
                
                await ctx.send(response)
    
    async def start(self):
        """Start the Discord bot."""
        if not self.bot or not self.token:
            await self.initialize()
        
        # Run the bot in a background task
        self.task = asyncio.create_task(self.bot.start(self.token))
        return self.task
    
    async def stop(self):
        """Stop the Discord bot."""
        if self.bot:
            await self.bot.close()
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
    
    def _load_discord_token(self) -> str:
        """
        Load the Discord bot token from a JSON configuration file.

        :return: Discord bot token string.
        :raises FileNotFoundError: If the config file is not found.
        :raises KeyError: If the expected token key is missing.
        """
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            config = json.load(f)

        if 'discord_bot_token' not in config:
            raise KeyError("Missing 'discord_bot_token' in config file.")
        
        return config['discord_bot_token']

    def _execute_ai_agent(self, query: str) -> str:
        """
        Runs your AI agent locally using OpenAI API and MCP.
        This is a synchronous version that blocks until the response is ready.

        :param query: Command or message from Discord.
        :return: Response from AI agent.
        """
        # Get the GPT handler
        gpt_handler = get_gpt_handler()
        
        # Call GPT and wait for the response
        return gpt_handler.ask_gpt_sync(query)


# For backward compatibility when running directly
if __name__ == '__main__':
    # Create and run the Discord event listener
    async def main():
        listener = DiscordEventListener()
        await listener.initialize()
        await listener.start()
        
        # Keep running until interrupted
        try:
            print("Discord bot is running. Press Ctrl+C to exit.")
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            await listener.stop()
    
    # Run the async main function
    asyncio.run(main())
