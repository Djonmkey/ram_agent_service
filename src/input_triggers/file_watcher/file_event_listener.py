import os
import sys
import asyncio
import time
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

# Add parent directory to path to import from main module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from input_triggers.input_triggers import EventListener
from gpt_thread import get_gpt_handler

class FileWatcherEventListener(EventListener):
    """
    A file-based event listener that watches a directory for new files
    and processes them with GPT.
    """
    
    def __init__(self, watch_dir: str = None, polling_interval: int = 5):
        """
        Initialize the file watcher event listener.
        
        Args:
            watch_dir: Directory to watch for new files. Defaults to 'watch' in the same directory.
            polling_interval: How often to check for new files in seconds.
        """
        self._name = "FileWatcher"
        self.watch_dir = watch_dir or os.path.join(os.path.dirname(__file__), 'watch')
        self.polling_interval = polling_interval
        self.processed_files = set()
        self.running = False
        self.task = None
    
    @property
    def name(self) -> str:
        """Get the name of the event listener."""
        return self._name
    
    async def initialize(self):
        """Initialize the file watcher."""
        # Create watch directory if it doesn't exist
        os.makedirs(self.watch_dir, exist_ok=True)
        
        # Initialize processed files set with existing files
        for file in os.listdir(self.watch_dir):
            file_path = os.path.join(self.watch_dir, file)
            if os.path.isfile(file_path):
                self.processed_files.add(file)
        
        print(f"File watcher initialized. Watching directory: {self.watch_dir}")
        print(f"Place text files in this directory to have them processed by GPT.")
    
    async def start(self):
        """Start watching for file events."""
        if self.running:
            return
        
        self.running = True
        self.task = asyncio.create_task(self._watch_loop())
        return self.task
    
    async def stop(self):
        """Stop watching for file events."""
        self.running = False
        
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
    
    async def _watch_loop(self):
        """Main loop for watching files."""
        while self.running:
            try:
                await self._check_for_new_files()
            except Exception as e:
                print(f"Error in file watcher: {e}")
            
            # Wait for the next check
            await asyncio.sleep(self.polling_interval)
    
    async def _check_for_new_files(self):
        """Check for new files in the watch directory."""
        current_files = set()
        
        for file in os.listdir(self.watch_dir):
            file_path = os.path.join(self.watch_dir, file)
            
            if os.path.isfile(file_path):
                current_files.add(file)
                
                # If this is a new file that hasn't been processed
                if file not in self.processed_files:
                    # Process new file
                    await self._process_file(file_path)
                    self.processed_files.add(file)
    
    async def _process_file(self, file_path: str):
        """
        Process a new file.
        
        Args:
            file_path: Path to the file to process.
        """
        # Only process text files
        if not file_path.endswith(('.txt', '.md')):
            print(f"Skipping non-text file: {file_path}")
            return
        
        try:
            print(f"Processing new file: {file_path}")
            
            # Read the file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if not content.strip():
                print(f"File is empty, skipping: {file_path}")
                return
            
            # Create a response file name
            file_name = os.path.basename(file_path)
            response_file_name = f"response_{file_name}"
            response_path = os.path.join(os.path.dirname(file_path), response_file_name)
            
            # Process with GPT
            # Using sync approach for simplicity
            response = self._process_with_gpt(content)
            
            # Write the response to a new file
            with open(response_path, 'w', encoding='utf-8') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"Response generated on {timestamp}\n\n")
                f.write(response)
            
            print(f"Processed file {file_path}. Response written to {response_path}")
            
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
    
    def _process_with_gpt(self, content: str) -> str:
        """
        Process content with GPT.
        
        Args:
            content: The content to process.
            
        Returns:
            The response from GPT.
        """
        gpt_handler = get_gpt_handler()
        
        # We'll wrap the content to make it clear this is a file processing request
        prompt = f"The following is the content of a file that was placed in a watched directory for processing. Please analyze or respond to this content as appropriate:\n\n{content}"
        
        return gpt_handler.ask_gpt_sync(prompt)


if __name__ == '__main__':
    # For testing the file watcher independently
    async def main():
        watcher = FileWatcherEventListener()
        await watcher.initialize()
        await watcher.start()
        
        try:
            print(f"File watcher is running. Watching directory: {watcher.watch_dir}")
            print("Press Ctrl+C to exit.")
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            await watcher.stop()
    
    # Run the async main function
    asyncio.run(main())
