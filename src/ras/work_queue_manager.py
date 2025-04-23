"""
work_queue_manager.py

This module provides global thread-safe queues for managing asynchronous work
across different components of a configuration-driven agent system. Each queue
represents a functional domain (e.g., chat model, input trigger) and supports
threaded execution of dynamically loaded Python modules on FIFO dequeued tasks.

Author: David McKee
"""

import sys
import threading
import queue
import json
import importlib

from typing import Callable, Dict, Any
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent # Go up three levels: discord -> input_triggers -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ras.agent_config_buffer import get_chat_model_config

# Global thread-safe work queues
chat_model_request_queue: queue.Queue[str] = queue.Queue()
chat_model_response_queue: queue.Queue[str] = queue.Queue()
input_trigger_queue: queue.Queue[str] = queue.Queue()
output_action_queue: queue.Queue[str] = queue.Queue()
tools_and_data_queue: queue.Queue[str] = queue.Queue()

QUEUE_NAME_CHAT_MODEL_REQUEST = "ChatModelRequest"
QUEUE_NAME_CHAT_MODEL_RESPONSE = "ChatModelResponse"
QUEUE_NAME_INPUT_TRIGGER = "InputTrigger"
QUEUE_NAME_OUTPUT_ACTION = "OutputAction"
QUEUE_NAME_TOOLS_AND_DATA = "ToolsAndData"

def enqueue_chat_model_request(agent_name: str, prompt: str) -> None:
    """
    Enqueue work for the chat model queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    
    message = {}
    message["agent_name"] = agent_name
    message["prompt"] = prompt
    
    contents = json.dumps(message)

    chat_model_request_queue.put(contents)

def enqueue_chat_model_response(agent_name: str, response: str) -> None:
    """
    Enqueue work for the chat model queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    
    message = {}
    message["agent_name"] = agent_name
    message["response"] = response
    
    contents = json.dumps(message)

    chat_model_response_queue.put(contents)


def enqueue_input_trigger(agent_name: str, contents: Dict) -> None:
    """
    Enqueue work for the input trigger queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    contents["agent_name"] = agent_name
    
    json_string = json.dumps(contents) 

    input_trigger_queue.put(json_string)


def enqueue_output_action(agent_name: str, contents: str) -> None:
    """
    Enqueue work for the output action queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    output_action_queue.put(contents)


def enqueue_tools_and_data(agent_name: str, contents: str) -> None:
    """
    Enqueue work for the tools and data queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    tools_and_data_queue.put(contents)

def process_chat_model_request(task_data: dict):
    agent_name = task_data["agent_name"]
    prompt = task_data["prompt"]
    chat_model_config = get_chat_model_config(agent_name)
    python_code_module = chat_model_config["python_code_module"]
    function_name = chat_model_config.get("handler_function", "ask_chat_model")

    # Convert file path to module path
    # Example: "src/chat_models/chat_model_openai.py" -> "chat_models.chat_model_openai"
    if python_code_module.endswith(".py"):
        python_code_module = python_code_module[:-3]  # Remove .py extension
    module_path = python_code_module.replace("/", ".")
    
    # If it starts with src/, remove that prefix for proper importing
    if module_path.startswith("src."):
        module_path = module_path[4:]

    # Dynamically import the module
    module = importlib.import_module(module_path)
    
    # If we're dealing with a class that needs to be instantiated
    if function_name == "ask_chat_model" and hasattr(module, "get_gpt_handler"):
        # Get or create the handler instance
        handler = module.get_gpt_handler(agent_name)
        # Call the method on the instance
        thread = threading.Thread(target=handler.ask_chat_model, args=(prompt,), daemon=True)
    else:
        # For functions that don't require a class instance
        func: Callable = getattr(module, function_name)
        thread = threading.Thread(target=func, args=(agent_name, prompt), daemon=True)
    
    thread.start()

def process_input_trigger(task_data: dict):
    # TODO: CHECK FOR INPUT AUGMENTATION
    # IF INPUT AUGMENTATION, TRIGGER INPUT AUGMENTATION
    # ELSE
    # MAKE CHAT MODEL REQUEST
    process_chat_model_request(task_data)

def process_chat_model_response(task_data: dict):
    pass 

def process_output_action(task_data: dict):
    pass 

def process_tools_and_data(task_data: dict):
    pass 


def _load_and_execute_module(queue_name: str, task_data: dict) -> None:
    """
    Dynamically load a Python module and execute a function within it.

    :param module_path: Dot-separated path to the Python module (e.g., "my_package.my_module")
    :param function_name: Function to invoke within the module
    :param task_data: Dictionary of task input parameters
    """
    try:
        if queue_name == QUEUE_NAME_CHAT_MODEL_REQUEST:
           process_chat_model_request(task_data)

        if queue_name == QUEUE_NAME_CHAT_MODEL_RESPONSE:
           process_chat_model_response(task_data)

        if queue_name == QUEUE_NAME_INPUT_TRIGGER:
           process_input_trigger(task_data)

        if queue_name == QUEUE_NAME_OUTPUT_ACTION:  
           process_output_action(task_data)

        if queue_name == QUEUE_NAME_TOOLS_AND_DATA:
           process_tools_and_data(task_data)

    except Exception as e:
        print(f"[ERROR] Failed to process {queue_name}.: {e}")


def _start_queue_worker(queue_name: str, task_queue: queue.Queue[str]) -> None:
    """
    Start a background thread that dequeues and processes tasks for a queue.

    :param name: Human-readable name of the queue for logging
    :param task_queue: The queue instance to monitor
    """
    def worker_loop():
        while True:
            try:
                task_json = task_queue.get()
                task = json.loads(task_json)
                _load_and_execute_module(queue_name, task)
            except Exception as e:
                print(f"[ERROR] {queue_name} queue processing failed: {e}")

    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()


def start_all_queue_workers() -> None:
    """
    Start background worker threads for each queue.
    """
    _start_queue_worker(QUEUE_NAME_CHAT_MODEL_REQUEST, chat_model_request_queue)
    _start_queue_worker(QUEUE_NAME_CHAT_MODEL_RESPONSE, chat_model_response_queue)
    _start_queue_worker(QUEUE_NAME_INPUT_TRIGGER, input_trigger_queue)
    _start_queue_worker(QUEUE_NAME_OUTPUT_ACTION, output_action_queue)
    _start_queue_worker(QUEUE_NAME_TOOLS_AND_DATA, tools_and_data_queue)
