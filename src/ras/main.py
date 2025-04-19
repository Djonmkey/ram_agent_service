import asyncio
import os
import sys
import json
import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog
from datetime import datetime
import threading
from pathlib import Path
import time
import queue
from startup import on_startup_dispatcher

# Add the event_listeners directory to the path
sys.path.append(os.path.join(os.path.dirname(__file__), 'event_listeners'))

# Import the main function from event_listeners_main.py
from event_listeners_main import main as event_listeners_main, listeners

# Global variables
running_listeners = {}
log_directory = os.path.join(os.path.dirname(__file__), 'logs')
current_conversations = {}

class ConversationLogger:
    """Handles logging of conversations from event listeners."""
    
    @staticmethod
    def log_conversation(event_listener_name, request, response, begin_time=None):
        """
        Log a conversation to a JSON file.
        
        Args:
            event_listener_name: Name of the event listener
            request: The request sent to the event listener
            response: The response from the event listener
            begin_time: Optional datetime when the request was sent. If None, current time is used.
        """
        # Record end time
        end_time = datetime.now()
        
        # If begin_time wasn't provided, use end_time (less accurate but prevents errors)
        if begin_time is None:
            begin_time = end_time
        
        # Calculate duration in seconds
        duration = (end_time - begin_time).total_seconds()
        
        # Create the log directory structure
        year = end_time.strftime("%Y")
        month = end_time.strftime("%m")
        day = end_time.strftime("%d")
        timestamp = end_time.strftime("%H_%M_%S_%f")[:-3]  # Hour, minute, second, millisecond
        
        log_path = os.path.join(log_directory, event_listener_name, year, month, day)
        os.makedirs(log_path, exist_ok=True)
        
        # Create the log file
        log_file = os.path.join(log_path, f"{timestamp}_conversation.json")
        
        # Create the log data
        log_data = {
            "timestamp": end_time.isoformat(),
            "begin_time": begin_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": duration,
            "event_listener": event_listener_name,
            "request": request,
            "response": response
        }
        
        # Write the log data to the file
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2)
        
        # Update the current conversation
        current_conversations[event_listener_name] = {
            "timestamp": end_time.isoformat(),
            "begin_time": begin_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration": duration,
            "request": request,
            "response": response,
            "log_file": log_file
        }
        
        # Signal the UI to update
        if hasattr(sys, 'ui_update_queue') and sys.ui_update_queue:
            sys.ui_update_queue.put(("conversation_update", event_listener_name))
        
        return log_file

    @staticmethod
    def get_conversation_logs(event_listener_name=None, limit=10):
        """
        Get the most recent conversation logs.
        
        Args:
            event_listener_name: Optional name of the event listener to filter by
            limit: Maximum number of logs to return
            
        Returns:
            A list of log file paths
        """
        logs = []
        
        # Define the base directory to search
        base_dir = os.path.join(log_directory, event_listener_name) if event_listener_name else log_directory
        
        if not os.path.exists(base_dir):
            return logs
        
        # Walk through the directory structure
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file.endswith("_conversation.json"):
                    logs.append(os.path.join(root, file))
        
        # Sort logs by modification time (newest first)
        logs.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # Limit the number of logs
        return logs[:limit]

    @staticmethod
    def load_conversation_log(log_file):
        """
        Load a conversation log from a file.
        
        Args:
            log_file: Path to the log file
            
        Returns:
            The conversation log data
        """
        if not os.path.exists(log_file):
            return None
        
        with open(log_file, 'r', encoding='utf-8') as f:
            return json.load(f)


# Monkey patch the GPT handler to log conversations
def patch_gpt_handler():
    """Patch the GPT handler to log conversations."""
    from gpt_thread import get_gpt_handler
    
    original_ask_gpt = get_gpt_handler().ask_gpt
    original_ask_gpt_sync = get_gpt_handler().ask_gpt_sync
    
    def patched_ask_gpt(prompt, callback=None):
        """Patched version of ask_gpt that logs conversations."""
        # Record begin time
        begin_time = datetime.now()
        
        # Determine which event listener is making the request
        frame = sys._getframe(1)
        event_listener_name = "Unknown"
        
        while frame:
            if 'self' in frame.f_locals and hasattr(frame.f_locals['self'], 'name'):
                event_listener_name = frame.f_locals['self'].name
                break
            frame = frame.f_back
        
        def wrapped_callback(response):
            """Wrap the callback to log the conversation."""
            # Log the conversation with begin_time
            ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
            
            # Call the original callback
            if callback:
                callback(response)
        
        # Call the original method with our wrapped callback
        return original_ask_gpt(prompt, wrapped_callback)
    
    def patched_ask_gpt_sync(prompt):
        """Patched version of ask_gpt_sync that logs conversations."""
        # Record begin time
        begin_time = datetime.now()
        
        # Determine which event listener is making the request
        frame = sys._getframe(1)
        event_listener_name = "Unknown"
        
        while frame:
            if 'self' in frame.f_locals and hasattr(frame.f_locals['self'], 'name'):
                event_listener_name = frame.f_locals['self'].name
                break
            frame = frame.f_back
        
        # Call the original method
        response = original_ask_gpt_sync(prompt)
        
        # Log the conversation with begin_time
        ConversationLogger.log_conversation(event_listener_name, prompt, response, begin_time)
        
        return response
    
    # Replace the original methods with our patched versions
    get_gpt_handler().ask_gpt = patched_ask_gpt
    get_gpt_handler().ask_gpt_sync = patched_ask_gpt_sync


class EventListenerUI(tk.Tk):
    """Main UI for displaying event listeners and conversations."""
    
    def __init__(self):
        super().__init__()
        
        self.title("Event Listener Dashboard")
        self.geometry("1000x800")
        
        # Create a queue for UI updates
        self.update_queue = queue.Queue()
        sys.ui_update_queue = self.update_queue
        
        # Create the main frame
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Create a paned window to split the UI
        self.paned_window = ttk.PanedWindow(self.main_frame, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)
        
        # Create the left frame for event listeners
        self.left_frame = ttk.Frame(self.paned_window, width=300)
        self.paned_window.add(self.left_frame, weight=1)
        
        # Create the right frame for conversations
        self.right_frame = ttk.Frame(self.paned_window, width=700)
        self.paned_window.add(self.right_frame, weight=2)
        
        # Set up the left frame (event listeners)
        self.setup_left_frame()
        
        # Set up the right frame (conversations)
        self.setup_right_frame()
        
        # Start checking for UI updates
        self.check_updates()
    
    def setup_left_frame(self):
        """Set up the left frame with event listener list."""
        # Create a label
        ttk.Label(self.left_frame, text="Running Event Listeners", font=("Arial", 14, "bold")).pack(pady=(0, 10), anchor=tk.W)
        
        # Create a frame for the event listener list
        list_frame = ttk.Frame(self.left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a scrollbar
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create the listbox
        self.listener_listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Arial", 12))
        self.listener_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configure the scrollbar
        scrollbar.config(command=self.listener_listbox.yview)
        
        # Bind the listbox selection event
        self.listener_listbox.bind('<<ListboxSelect>>', self.on_listener_selected)
        
        # Create a frame for the log history
        history_frame = ttk.LabelFrame(self.left_frame, text="Conversation History")
        history_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # Create a scrollbar for the history listbox
        history_scrollbar = ttk.Scrollbar(history_frame)
        history_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create the history listbox
        self.history_listbox = tk.Listbox(history_frame, yscrollcommand=history_scrollbar.set, font=("Arial", 10))
        self.history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Configure the scrollbar
        history_scrollbar.config(command=self.history_listbox.yview)
        
        # Bind the history listbox selection event
        self.history_listbox.bind('<<ListboxSelect>>', self.on_history_selected)
    
    def setup_right_frame(self):
        """Set up the right frame with conversation display."""
        # Create a label
        self.conversation_label = ttk.Label(self.right_frame, text="Select an event listener", font=("Arial", 14, "bold"))
        self.conversation_label.pack(pady=(0, 10), anchor=tk.W)
        
        # Create a frame for the request
        request_frame = ttk.LabelFrame(self.right_frame, text="Request")
        request_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create a text widget for the request
        self.request_text = scrolledtext.ScrolledText(request_frame, wrap=tk.WORD, font=("Arial", 10))
        self.request_text.pack(fill=tk.BOTH, expand=True)
        self.request_text.config(state=tk.DISABLED)
        
        # Create a frame for the response
        response_frame = ttk.LabelFrame(self.right_frame, text="Response")
        response_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a text widget for the response
        self.response_text = scrolledtext.ScrolledText(response_frame, wrap=tk.WORD, font=("Arial", 10))
        self.response_text.pack(fill=tk.BOTH, expand=True)
        self.response_text.config(state=tk.DISABLED)
    
    def update_listener_list(self):
        """Update the event listener list."""
        self.listener_listbox.delete(0, tk.END)
        
        for name in sorted(listeners.keys()):
            self.listener_listbox.insert(tk.END, name)
    
    def on_listener_selected(self, event):
        """Handle event listener selection."""
        # Get the selected listener
        selection = self.listener_listbox.curselection()
        if not selection:
            return
        
        listener_name = self.listener_listbox.get(selection[0])
        
        # Update the conversation label
        self.conversation_label.config(text=f"{listener_name} - Latest Conversation")
        
        # Update the conversation display
        self.display_conversation(listener_name)
        
        # Update the history listbox
        self.update_history_listbox(listener_name)
    
    def update_history_listbox(self, listener_name):
        """Update the history listbox with logs for the selected listener."""
        self.history_listbox.delete(0, tk.END)
        
        # Get the logs for the selected listener
        logs = ConversationLogger.get_conversation_logs(listener_name)
        
        for log_file in logs:
            # Extract the timestamp from the filename
            filename = os.path.basename(log_file)
            timestamp = filename.split('_conversation.json')[0]
            
            # Format the timestamp for display
            try:
                parts = timestamp.split('_')
                if len(parts) >= 3:
                    display_time = f"{parts[0]}:{parts[1]}:{parts[2]}"
                else:
                    display_time = timestamp
            except:
                display_time = timestamp
            
            # Add to the listbox with the full path as data
            self.history_listbox.insert(tk.END, display_time)
            self.history_listbox.itemconfig(tk.END, {'log_file': log_file})
    
    def on_history_selected(self, event):
        """Handle history selection."""
        # Get the selected history item
        selection = self.history_listbox.curselection()
        if not selection:
            return
        
        # Get the log file path
        index = selection[0]
        log_file = self.history_listbox.itemcget(index, 'log_file')
        
        if not log_file:
            return
        
        # Load and display the conversation
        self.display_conversation_from_file(log_file)
    
    def display_conversation(self, listener_name):
        """Display the latest conversation for the selected listener."""
        if listener_name not in current_conversations:
            # Clear the display
            self.request_text.config(state=tk.NORMAL)
            self.request_text.delete(1.0, tk.END)
            self.request_text.insert(tk.END, "No conversations yet.")
            self.request_text.config(state=tk.DISABLED)
            
            self.response_text.config(state=tk.NORMAL)
            self.response_text.delete(1.0, tk.END)
            self.response_text.insert(tk.END, "No conversations yet.")
            self.response_text.config(state=tk.DISABLED)
            return
        
        # Get the conversation
        conversation = current_conversations[listener_name]
        
        # Update the request text
        self.request_text.config(state=tk.NORMAL)
        self.request_text.delete(1.0, tk.END)
        self.request_text.insert(tk.END, conversation["request"])
        self.request_text.config(state=tk.DISABLED)
        
        # Update the response text
        self.response_text.config(state=tk.NORMAL)
        self.response_text.delete(1.0, tk.END)
        self.response_text.insert(tk.END, conversation["response"])
        self.response_text.config(state=tk.DISABLED)
    
    def display_conversation_from_file(self, log_file):
        """Display a conversation from a log file."""
        # Load the conversation
        conversation = ConversationLogger.load_conversation_log(log_file)
        
        if not conversation:
            return
        
        # Update the conversation label
        self.conversation_label.config(text=f"{conversation['event_listener']} - {conversation['timestamp']}")
        
        # Update the request text
        self.request_text.config(state=tk.NORMAL)
        self.request_text.delete(1.0, tk.END)
        self.request_text.insert(tk.END, conversation["request"])
        self.request_text.config(state=tk.DISABLED)
        
        # Update the response text
        self.response_text.config(state=tk.NORMAL)
        self.response_text.delete(1.0, tk.END)
        self.response_text.insert(tk.END, conversation["response"])
        self.response_text.config(state=tk.DISABLED)
    
    def check_updates(self):
        """Check for UI updates from the queue."""
        try:
            while True:
                # Get an update from the queue (non-blocking)
                update = self.update_queue.get_nowait()
                
                if update[0] == "listener_update":
                    # Update the listener list
                    self.update_listener_list()
                elif update[0] == "conversation_update":
                    # Update the conversation display if the updated listener is selected
                    selection = self.listener_listbox.curselection()
                    if selection and self.listener_listbox.get(selection[0]) == update[1]:
                        self.display_conversation(update[1])
                        self.update_history_listbox(update[1])
                
                # Mark the update as done
                self.update_queue.task_done()
        except queue.Empty:
            # No more updates, schedule the next check
            self.after(100, self.check_updates)


async def run_event_listeners():
    """Run the event listeners in the background."""
    # Create the log directory
    os.makedirs(log_directory, exist_ok=True)
    
    # Patch the GPT handler to log conversations
    patch_gpt_handler()
    
    # Run the event listeners main function
    await event_listeners_main()


def start_event_listeners():
    """Start the event listeners in a separate thread."""
    asyncio.run(run_event_listeners())


if __name__ == "__main__":
    # Execute MCP startup initialization (index reloads, etc.)
    on_startup_dispatcher()

    # Create a queue for UI updates
    sys.ui_update_queue = queue.Queue()
    
    # Start the event listeners in a separate thread
    threading.Thread(target=start_event_listeners, daemon=True).start()

    # Create and run the UI
    app = EventListenerUI()
    app.mainloop()
