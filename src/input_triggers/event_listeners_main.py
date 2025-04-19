import asyncio
import importlib
import os
import sys
from typing import List, Dict, Any, Optional, Type

from event_listener import EventListener
from gpt_thread import get_gpt_handler

# Dictionary to store loaded event listeners
listeners: Dict[str, EventListener] = {}

def ask_gpt(prompt: str) -> str:
    """
    Send a request to the GPT model and wait for the response.
    This is a synchronous wrapper around the asynchronous GPT handler.
    
    Args:
        prompt: The prompt to send to the GPT model.
        
    Returns:
        The response from the GPT model.
    """
    gpt_handler = get_gpt_handler()
    return gpt_handler.ask_gpt_sync(prompt)

def ask_gpt_async(prompt: str, callback=None):
    """
    Queue a request to the GPT model without waiting for the response.
    
    Args:
        prompt: The prompt to send to the GPT model.
        callback: Optional callback function to call with the response.
    """
    gpt_handler = get_gpt_handler()
    gpt_handler.ask_gpt(prompt, callback)

def discover_event_listeners() -> List[Type[EventListener]]:
    """
    Discover and load all event listener implementations.
    
    Returns:
        A list of EventListener classes.
    """
    listener_classes = []
    
    # Look for modules that might contain event listeners
    for root, dirs, files in os.walk('.'):
        # Skip __pycache__ and hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('__') and not d.startswith('.')]
        
        for file in files:
            # Skip non-Python files and this file itself
            if not file.endswith('.py') or file == os.path.basename(__file__):
                continue
            
            # Convert path to module format
            module_path = os.path.join(root, file)
            module_path = module_path.replace(os.path.sep, '.').replace('..', '').rstrip('.py')
            if module_path.startswith('.'):
                module_path = module_path[1:]
                
            try:
                # Dynamically import the module and look for EventListener subclasses
                module = importlib.import_module(module_path)
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    
                    # Check if it's a class, a subclass of EventListener, and not EventListener itself
                    if (isinstance(attr, type) and 
                        issubclass(attr, EventListener) and 
                        attr is not EventListener):
                        listener_classes.append(attr)
            except (ImportError, AttributeError) as e:
                print(f"Error loading module {module_path}: {e}")
    
    return listener_classes

async def load_event_listeners():
    """
    Load and initialize all event listeners.
    """
    print("Discovering event listeners...")
    listener_classes = discover_event_listeners()
    
    if not listener_classes:
        print("No event listeners found.")
        return
    
    print(f"Found {len(listener_classes)} event listener(s):")
    for cls in listener_classes:
        print(f"  - {cls.__name__}")
    
    # Initialize each listener
    for listener_class in listener_classes:
        try:
            listener = listener_class()
            print(f"Initializing {listener.name} event listener...")
            await listener.initialize()
            listeners[listener.name] = listener
        except Exception as e:
            print(f"Failed to initialize {listener_class.__name__}: {e}")

async def start_event_listeners():
    """
    Start all initialized event listeners.
    """
    if not listeners:
        print("No listeners to start.")
        return
    
    print(f"Starting {len(listeners)} event listener(s)...")
    
    # Start each listener
    for name, listener in listeners.items():
        try:
            print(f"Starting {name} event listener...")
            await listener.start()
        except Exception as e:
            print(f"Failed to start {name}: {e}")

async def stop_event_listeners():
    """
    Stop all running event listeners.
    """
    if not listeners:
        return
    
    print(f"Stopping {len(listeners)} event listener(s)...")
    
    # Stop each listener
    for name, listener in listeners.items():
        try:
            print(f"Stopping {name} event listener...")
            await listener.stop()
        except Exception as e:
            print(f"Error stopping {name}: {e}")

async def main():
    """
    Main entry point for the application.
    """
    try:
        # Load and start all event listeners
        await load_event_listeners()
        await start_event_listeners()
        
        # Keep the main thread alive
        print("All event listeners started. Press Ctrl+C to exit.")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        # Ensure proper cleanup
        await stop_event_listeners()
        
        # Clean shutdown of GPT handler
        gpt_handler = get_gpt_handler()
        gpt_handler.shutdown()

# Example of direct usage
if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
