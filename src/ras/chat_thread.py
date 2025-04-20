import openai
import json
import threading
import queue
import asyncio
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, Any, Optional


class GPTRequest:
    """Represents a request to the GPT model."""
    def __init__(self, prompt: str, callback: Optional[Callable[[str], None]] = None):
        self.prompt = prompt
        self.callback = callback

class GPTThreadHandler:
    """Handles GPT requests on a separate thread."""
    
    def __init__(self, agent_config_data: Dict[str, Any]):
        # Load config from gpt.json
        with open("event_listeners/gpt.json", "r") as f:
            config = json.load(f)
            self.api_key = config["api_key"]
            self.model = config["model"]
            self.temperature = config.get("temperature", 0.7)
            self.max_tokens = config.get("max_tokens", 1000)
        
        # Load base system instructions
        with open("event_listeners/gpt_system_instructions.txt", "r") as f:
            base_instructions = f.read()

        # Load available MCP commands
        command_data_path = agent_config_data.get("mcp_commands_config_file")

        with open(command_data_path, "r") as f:
            command_data = json.load(f)

        # Format MCP commands for GPT, including optional response format
        command_descriptions = "\n".join(
            f"{cmd['system_text']}: {cmd['system_description']}"
            + (f" (Response format: {cmd['response_format']})" if cmd.get("response_format") else "")
            for cmd in command_data.get("mcp_commands", [])
        )

        self.system_content = (
            f"{base_instructions.strip()}\n\n"
            f"Available MCP commands:\n{command_descriptions}"
        )
        
        # Initialize the client with explicit api_key
        self.client = openai.OpenAI(api_key=self.api_key)
        
        # Create a queue for GPT requests
        self.request_queue = queue.Queue()
        
        # Create a thread pool for processing requests
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Start the worker thread
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()
    
    def _process_queue(self):
        """Process requests from the queue in a separate thread."""
        while True:
            try:
                request = self.request_queue.get()
                if request is None:  # None is a signal to stop the thread
                    break
                
                # Submit the request to the thread pool
                self.executor.submit(self._process_request, request)
                
            except Exception as e:
                print(f"Error processing GPT request queue: {e}")
            finally:
                self.request_queue.task_done()
    
    def _process_request(self, request: GPTRequest):
        """Process a single GPT request."""
        try:
            # Ensure there's an event loop available in this thread
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                # If there's no event loop, create a new one and set it as the current one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            response = self._ask_gpt(request.prompt)
            
            # If a callback was provided, call it with the response
            if request.callback:
                request.callback(response)
                
        except Exception as e:
            print(f"Error processing GPT request: {e}")
            # Call the callback with the error if one was provided
            if request.callback:
                request.callback(f"Error: {e}")
    
    def _ask_gpt(self, prompt: str) -> str:
        """Send a request to the GPT model."""
        # Create request parameters
        request_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_content},
                {"role": "user", "content": prompt}
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        
        # Send the request
        chat_completion = self.client.chat.completions.create(**request_params)
        
        # Get the response content
        response_content = chat_completion.choices[0].message.content
        
        # Log the request and response to a file
        self._log_raw_chat(request_params, chat_completion)
        
        return response_content
    
    def _log_raw_chat(self, request_params: Dict[str, Any], response):
        """
        Log the raw chat request and response to a JSON file.
        
        Args:
            request_params: The parameters sent to the GPT API
            response: The response from the GPT API
        """
        try:
            # Create the log directory structure
            now = datetime.now()
            year = now.strftime("%Y")
            month = now.strftime("%m")
            day = now.strftime("%d")
            timestamp = now.strftime("%H_%M_%S_%f")[:-3]  # Hour, minute, second, millisecond
            
            log_path = os.path.join("logs", "RawChat", year, month, day)
            os.makedirs(log_path, exist_ok=True)
            
            # Create the log file
            log_file = os.path.join(log_path, f"{timestamp}_raw_chat.json")
            
            # Convert response to a serializable format
            response_dict = {
                "id": response.id,
                "model": response.model,
                "object": response.object,
                "created": response.created,
                "choices": [{
                    "index": choice.index,
                    "message": {
                        "role": choice.message.role,
                        "content": choice.message.content
                    },
                    "finish_reason": choice.finish_reason
                } for choice in response.choices],
                "usage": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens
                }
            }
            
            # Create the log data
            log_data = {
                "timestamp": now.isoformat(),
                "request": request_params,
                "response": response_dict
            }
            
            # Write the log data to the file
            with open(log_file, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, indent=2)
                
        except Exception as e:
            print(f"Error logging raw chat: {e}")
    
    def ask_gpt(self, prompt: str, callback: Optional[Callable[[str], None]] = None):
        """
        Queue a request to the GPT model.
        
        Args:
            prompt: The prompt to send to the GPT model.
            callback: Optional callback function to call with the response.
        """
        request = GPTRequest(prompt, callback)
        self.request_queue.put(request)
    
    def ask_gpt_sync(self, prompt: str) -> str:
        """
        Send a request to the GPT model and wait for the response.
        This method blocks until the response is received.
        
        Args:
            prompt: The prompt to send to the GPT model.
            
        Returns:
            The response from the GPT model.
        """
        response_queue = queue.Queue()
        
        def callback(response: str):
            response_queue.put(response)
        
        self.ask_gpt(prompt, callback)
        
        # Wait for the response
        return response_queue.get()
    
    def shutdown(self):
        """Shutdown the thread handler."""
        # Signal the worker thread to stop
        self.request_queue.put(None)
        
        # Wait for the worker thread to finish
        self.worker_thread.join()
        
        # Shutdown the thread pool
        self.executor.shutdown()

# Singleton instance
_gpt_handler = None

def get_gpt_handler(agent_config_data: Dict[str, Any]) -> GPTThreadHandler:
    """Get the singleton instance of the GPTThreadHandler."""
    global _gpt_handler
    if _gpt_handler is None:
        _gpt_handler = GPTThreadHandler(agent_config_data)
    return _gpt_handler
