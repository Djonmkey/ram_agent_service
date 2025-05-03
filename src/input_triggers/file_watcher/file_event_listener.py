# src/input_triggers/file_watcher/file_event_listener.py
import asyncio
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent, FileCreatedEvent, FileModifiedEvent
from typing import Optional, Dict, Any, List, Set
from pathlib import Path
from datetime import datetime, timezone
import base64

# Ensure src is in path for sibling imports
import sys
SRC_DIR = Path(__file__).resolve().parent.parent.parent # Go up three levels: file_watcher -> input_triggers -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from input_triggers.input_triggers import InputTrigger
from ras import work_queue_manager

# Default debounce time in seconds (can be overridden in trigger config)
DEFAULT_DEBOUNCE_SECONDS = 1.0

class FileChangeHandler(FileSystemEventHandler):
    """Handles file system events detected by watchdog."""

    def __init__(self, listener_instance: 'FileEventListener'):
        self.listener = listener_instance
        self.logger = listener_instance.logger # Use listener's logger
        self.debounce_cache: Dict[Path, asyncio.TimerHandle] = {}
        self.debounce_seconds = listener_instance.debounce_seconds

    def _schedule_processing(self, event_path: Path, event_type: str):
        """Schedules processing after a debounce period."""
        path_obj = Path(event_path)

        # Cancel any existing timer for this path
        if path_obj in self.debounce_cache:
            self.debounce_cache[path_obj].cancel()
            self.logger.debug(f"Debounce timer cancelled for: {path_obj}")

        # Schedule new processing call
        loop = asyncio.get_running_loop()
        self.debounce_cache[path_obj] = loop.call_later(
            self.debounce_seconds,
            self._process_debounced_event,
            path_obj,
            event_type
        )
        self.logger.debug(f"Processing scheduled for '{path_obj}' ({event_type}) in {self.debounce_seconds}s")

    def _process_debounced_event(self, path: Path, event_type: str):
        """Called after debounce timeout."""
        self.logger.debug(f"Debounce finished for: {path} ({event_type})")
        # Remove from cache now that it's being processed
        self.debounce_cache.pop(path, None)
        # Call the listener's processing method in the main event loop
        asyncio.run_coroutine_threadsafe(
            self.listener.process_file_event(str(path), event_type),
            self.listener.loop # Use the listener's loop
        )

    def _should_process_file_event(self, file_path: Path) -> bool:
        """
        Determines if a file event should be processed based on our watch configuration.
        
        Args:
            file_path: The resolved Path object of the file that triggered the event
            
        Returns:
            bool: True if the event should be processed, False otherwise
        """
        # If we have specific files to watch, check if this file matches any of them
        if self.listener.resolved_watch_files:
            # Compare normalized string paths for more reliable matching
            file_path_str = str(file_path).lower()
            for watch_file in self.listener.resolved_watch_files:
                if str(watch_file).lower() == file_path_str:
                    return True
                
            # If not a specific watched file, check if it's in a watched directory
            for dir_path in self.listener.resolved_watch_directories:
                if str(file_path).startswith(str(dir_path)):
                    return True
                
            # Not in our watched files or directories
            return False
        
        # If we don't have specific files to watch, check if it's in a watched directory
        elif self.listener.resolved_watch_directories:
            for dir_path in self.listener.resolved_watch_directories:
                if str(file_path).startswith(str(dir_path)):
                    return True
            return False
        
        # If we have neither watched files nor directories (shouldn't happen due to validation)
        return False

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            path = Path(event.src_path).resolve()
            
            # Check if we should process this file event
            if not self._should_process_file_event(path):
                return
            
            self.logger.debug(f"Watchdog detected creation: {event.src_path}")
            self._schedule_processing(event.src_path, "created")

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            path = Path(event.src_path).resolve()
            
            # Check if we should process this file event
            if not self._should_process_file_event(path):
                return
            
            self.logger.debug(f"Watchdog detected modification: {event.src_path}")
            self._schedule_processing(event.src_path, "modified")

    # Optionally handle on_deleted and on_moved as needed
    # def on_deleted(self, event):
    #     if not event.is_directory:
    #         self.logger.info(f"Deleted: {event.src_path}")
    #         # Decide if deletion triggers AI processing

    # def on_moved(self, event):
    #     if not event.is_directory:
    #         self.logger.info(f"Moved: {event.src_path} to {event.dest_path}")
    #         # Decide if move triggers AI processing (e.g., on dest_path)


class FileEventListener(InputTrigger):
    """
    An input trigger that watches specified directories and/or individual files
    for file creation or modification events and processes them using an AI agent.
    """

    def __init__(
        self,
        agent_config_data: Dict[str, Any],
        trigger_config_data: Optional[Dict[str, Any]] = None,
        trigger_secrets: Optional[Dict[str, Any]] = None,
    ):
        """
        Initializes the FileEventListener.

        Args:
            agent_name: The name of the agent this trigger instance belongs to.
            trigger_config_data: Dictionary containing configuration for this trigger.
                                 Expected keys:
                                 - 'watch_directories': List of directory paths (strings) to monitor.
                                 - 'watch_files': List of specific file paths (strings) to monitor.
                                                  The parent directory of each file will be watched,
                                                  and events will be filtered to only process the specified files.
                                 - 'watch_patterns': (Optional) List of glob patterns (e.g., ['*.txt', '*.csv'])
                                                     to filter files within watched directories. If omitted,
                                                     all file events are considered.
                                 - 'recursive': (Optional) Boolean indicating whether to watch subdirectories (defaults to True).
                                                This only applies to watch_directories, not watch_files.
                                 - 'debounce_seconds': (Optional) Float seconds to wait after the last event before processing (defaults to 1.0).
            trigger_secrets: Dictionary containing secrets (not directly used by this trigger,
                             but passed for consistency).
        """
        super().__init__(agent_config_data, trigger_config_data, trigger_secrets)
        self.logger = logging.getLogger(f"{self.agent_name}.{self.name}") # Use specific logger

        # --- Configuration ---
        self.watch_directories: List[str] = self.trigger_config.get("watch_directories", [])
        self.watch_files: List[str] = self.trigger_config.get("watch_files", []) # Can be None or empty
        self.watch_patterns: Optional[List[str]] = self.trigger_config.get("watch_patterns") # Can be None
        self.recursive: bool = self.trigger_config.get("recursive", True)
        self.debounce_seconds: float = self.trigger_config.get("debounce_seconds", DEFAULT_DEBOUNCE_SECONDS)

        if not self.watch_directories and not self.watch_files:
             self.logger.error("Configuration error: 'watch_directories' and 'watch_files' lists are missing or empty.")
             # Consider raising ValueError if this is critical
             raise ValueError("'watch_directories' or 'watch_files' must be specified in the trigger configuration.")

        # Validate and resolve directory paths
        self.resolved_watch_directories: List[Path] = []
        for dir_path in self.watch_directories:
            path = Path(dir_path).resolve() # Resolve relative to CWD or expect absolute
            if not path.is_dir():
                 self.logger.warning(f"Watch directory does not exist or is not a directory: {path}. Skipping.")
            else:
                 self.resolved_watch_directories.append(path)

        # Validate and resolve file paths
        self.resolved_watch_files: List[Path] = []
        for file_path in self.watch_files:
            path = Path(file_path).resolve() # Resolve relative to CWD or expect absolute
            if not path.exists():
                 self.logger.warning(f"Watch file does not exist: {path}. Skipping.")
            elif not path.is_file():
                 self.logger.warning(f"Watch path is not a file: {path}. Skipping.")
            else:
                 self.resolved_watch_files.append(path)

        # Check if we have any valid paths to watch
        if not self.resolved_watch_directories and not self.resolved_watch_files:
             self.logger.error("No valid watch directories or files found after resolving paths.")
             raise ValueError("No valid paths specified in 'watch_directories' or 'watch_files'.")


        # --- Watchdog Setup ---
        self.event_handler = FileChangeHandler(self)
        self.observer = Observer()

        self.logger.info(f"File Event Listener configured for Agent '{self.agent_name}'")
        self.logger.info(f"  Watching Directories: {[str(p) for p in self.resolved_watch_directories]}")
        self.logger.info(f"  Watching Files: {[str(p) for p in self.resolved_watch_files]}")
        self.logger.info(f"  Recursive: {self.recursive}")
        self.logger.info(f"  Patterns: {self.watch_patterns if self.watch_patterns else 'All files'}")
        self.logger.info(f"  Debounce Time: {self.debounce_seconds}s")


    @property
    def name(self) -> str:
        return "FileEventListener"

    async def initialize(self):
        """Initializes the file watcher."""
        await super().initialize() # Gets loop, logs base init
        self.logger.info("Initializing File Event Listener...")

        # Schedule observers for directories
        for path in self.resolved_watch_directories:
            try:
                self.observer.schedule(self.event_handler, str(path), recursive=self.recursive)
                self.logger.info(f"Scheduled observer for directory: {path}")
            except Exception as e:
                self.logger.error(f"Failed to schedule observer for directory {path}: {e}", exc_info=True)
                # Log and continue trying others

        # Schedule observers for individual files
        for path in self.resolved_watch_files:
            try:
                # For individual files, we need to watch the parent directory
                # and filter events for the specific file
                parent_dir = path.parent
                self.observer.schedule(self.event_handler, str(parent_dir), recursive=False)
                self.logger.info(f"Scheduled observer for file: {path} (watching parent: {parent_dir})")
            except Exception as e:
                self.logger.error(f"Failed to schedule observer for file {path}: {e}", exc_info=True)
                # Log and continue trying others

        if not self.observer.emitters:
             self.logger.error("No observers were successfully scheduled.")
             raise RuntimeError("File watcher initialization failed: Could not schedule any observers.")

        self.logger.info("File Event Listener initialized.")


    async def start(self):
        """Starts the file system observer."""
        await super().start() # Log start message

        if not self.observer.is_alive():
            try:
                # The observer runs in its own thread, managed by the watchdog library.
                # We don't need to run it in a separate asyncio task.
                self.observer.start()
                self.logger.info("Watchdog observer thread started.")
                # Keep the trigger alive while the observer runs.
                # The observer thread will call event handlers, which then schedule
                # tasks in our main asyncio loop via run_coroutine_threadsafe.
            except Exception as e:
                 self.logger.error(f"Failed to start watchdog observer: {e}", exc_info=True)
                 raise RuntimeError(f"Could not start file observer: {e}")
        else:
            self.logger.warning("Watchdog observer is already running.")


    async def stop(self):
        """Stops the file system observer."""
        await super().stop() # Log stop message
        if self.observer.is_alive():
            self.logger.info("Stopping watchdog observer thread...")
            try:
                self.observer.stop()
                # Wait for the observer thread to finish
                self.observer.join(timeout=5.0)
                if self.observer.is_alive():
                     self.logger.warning("Watchdog observer thread did not stop within timeout.")
                else:
                     self.logger.info("Watchdog observer thread stopped.")
            except Exception as e:
                 self.logger.error(f"Error stopping watchdog observer: {e}", exc_info=True)
        else:
             self.logger.info("Watchdog observer was not running.")

        # Clean up debounce timers
        for timer in self.event_handler.debounce_cache.values():
             timer.cancel()
        self.event_handler.debounce_cache.clear()
        self.logger.debug("Cleared pending debounce timers.")

        self.logger.info("FileEventListener stopped.")


    def _matches_patterns(self, file_path: Path) -> bool:
        """Checks if the file path matches any of the watch patterns."""
        if not self.watch_patterns:
            return True # No patterns defined, match everything
        for pattern in self.watch_patterns:
            if file_path.match(pattern):
                return True
        return False

    async def process_file_event(self, file_path_str: str, event_type: str):
        """
        Processes a file event after debouncing. Reads the file content
        and triggers the AI agent.
        """
        file_path = Path(file_path_str)
        self.logger.info(f"Processing {event_type} event for: {file_path}")

        # Check against patterns (if any)
        if not self._matches_patterns(file_path):
            self.logger.debug(f"Skipping file {file_path} as it doesn't match patterns: {self.watch_patterns}")
            return

        try:
            # Check if file still exists (it might have been deleted quickly)
            if not file_path.is_file():
                 self.logger.warning(f"File no longer exists or is not a file: {file_path}. Skipping processing.")
                 return

            # Read file content
            # Consider adding encoding options or binary read based on config/file type
            try:
                content = file_path.read_text(encoding='utf-8')
                self.logger.debug(f"Read {len(content)} characters from {file_path}")
            except Exception as read_err:
                 self.logger.error(f"Error reading file {file_path}: {read_err}", exc_info=True)
                 return # Cannot process if read fails

            # Construct the initial query for the AI agent
            initial_query = (
                f"A file event occurred:\n"
                f"File Path: {file_path_str}\n"
                f"Event Type: {event_type}\n\n"
                f"File Content:\n"
                f"```\n{content}\n```\n\n"
                f"Please process this file event and its content."
            )

            # Define the callback for the AI response
            def file_event_callback(ai_response: str):
                meta_data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "file_path_str": file_path_str,
                    "event_type": event_type,
                    "encoding": "base64"
                }

                agent_name = self.agent_config_data["name"]

                def image_to_base64_str(image_path: str) -> str:
                    """
                    Convert an image file to a base64-encoded string.
                    
                    :param image_path: Path to the image file.
                    :return: Base64-encoded string representation of the image.
                    """
                    with open(image_path, "rb") as image_file:
                        encoded_bytes = base64.b64encode(image_file.read())
                        return encoded_bytes.decode("utf-8")
    
                message_content_image = image_to_base64_str(file_path_str)

                work_queue_manager.enqueue_input_trigger(
                    agent_name, message_content_image, meta_data
                )
                
                self.logger.info(f"AI processing finished for file event: {file_path_str} ({event_type})")

            # Execute the AI agent asynchronously
            self._execute_ai_agent_async(
                initial_query=initial_query,
                callback=file_event_callback
            )

        except Exception as e:
            self.logger.error(f"Error during processing of file event for {file_path_str}: {e}", exc_info=True)
