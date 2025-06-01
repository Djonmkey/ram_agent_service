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

from ras.agent_config_buffer import get_chat_model_config, get_output_action_config, get_input_augmentation_config
from tools_and_data.mcp_command_helper import contains_mcp_command, process_mcp_commands, escape_system_text_with_command_escape_text

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

def enqueue_chat_model_response(agent_name: str, response: str, meta_data: dict) -> None:
    """
    Enqueue work for the chat model queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    
    contents = {}
    contents["agent_name"] = agent_name
    contents["response"] = response
    contents["meta_data"] = meta_data
    
    json_string = json.dumps(contents)

    chat_model_response_queue.put(json_string)


def enqueue_input_trigger(agent_name: str, prompt: str, meta_data: Dict) -> None:
    """
    Enqueue work for the input trigger queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    contents = {}
    contents["agent_name"] = agent_name
    contents["prompt"] = prompt
    contents["meta_data"] = meta_data
  
    json_string = json.dumps(contents) 

    input_trigger_queue.put(json_string)


def enqueue_output_action(agent_name: str, chat_model_response: str, meta_data: Dict) -> None:
    """
    Enqueue work for the output action queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """

    message = {}
    message["agent_name"] = agent_name
    message["response"] = chat_model_response
    message["meta_data"] = meta_data
    
    contents = json.dumps(message)

    output_action_queue.put(contents)


def enqueue_tools_and_data(agent_name: str, contents: str) -> None:
    """
    Enqueue work for the tools and data queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    tools_and_data_queue.put(contents)

def get_python_code_module(python_code_module: str):
    """
    Get the Python code module for the given agent name.

    :param agent_name: Name of the agent
    :return: The Python code module path
    """
    # Convert file path to module path
    # Example: "src/chat_models/chat_model_openai.py" -> "chat_models.chat_model_openai"
    if python_code_module.endswith(".py"):
        python_code_module = python_code_module[:-3]  # Remove .py extension
    module_path = python_code_module.replace("/", ".")      # Unix-style path to dot notation
    module_path = module_path.replace("\\", ".")     # Windows-style path to dot notation

    # If it starts with src/, remove that prefix for proper importing
    if module_path.startswith("src."):
        module_path = module_path[4:]

    # Import the module dynamically
    module = importlib.import_module(module_path)
        
    return module

def process_chat_model_input_augmentation(task_data):
    agent_name = task_data["agent_name"]
    prompt = task_data["prompt"]    
    meta_data = task_data.get("meta_data", {})

    # Imporant: We are already in a thread
    input_augmentation_config = get_input_augmentation_config(agent_name)
    python_code_module = input_augmentation_config["python_code_module"]
    module = get_python_code_module(python_code_module)

    # Step 1: Execute Input Augmentation
    prompt = module.augment_prompt(agent_name, prompt, meta_data)

    # Step 2: Execute Chat Model Request
    task_data["prompt"] = prompt
    process_chat_model_request(task_data)


def process_chat_model_request(task_data: dict):
    agent_name = task_data["agent_name"]
    prompt = task_data["prompt"]    
    meta_data = task_data.get("meta_data", {})

    chat_model_config = get_chat_model_config(agent_name)
    python_code_module = chat_model_config["python_code_module"]

    # Import the module dynamically
    module = get_python_code_module(python_code_module)

    # Start the thread
    thread = threading.Thread(
        target=module.ask_chat_model,
        args=(agent_name, prompt, meta_data),
        daemon=True
    )

    thread.start()
    

def process_input_trigger(task_data: dict):
    agent_name = task_data["agent_name"]
    prompt = task_data["prompt"]    
    meta_data = task_data.get("meta_data", {})

    # Step 1: Execute Input Augmentation
    input_augmentation_config = get_input_augmentation_config(agent_name)

    if mcp_client_python_code_module:
        if input_augmentation_config:
            prompt = augment_input_prompt(agent_name, prompt, meta_data)
        
        # Check if the MCP client manager has a client for this agent
        if mcp_client_manager and mcp_client_manager.has_client(agent_name):
            # Run the async process_query method in a thread
            def run_async_process_query():
                try:
                    asyncio.run(mcp_client_manager.process_query(agent_name, prompt, meta_data))
                except Exception as e:
                    print(f"Error in MCP client process_query: {e}")
            
            thread = threading.Thread(target=run_async_process_query, daemon=True)
            thread.start()
        else:
            print(f"No MCPClient found for agent: {agent_name}")
    
    else:
        if input_augmentation_config:
            # Start the thread
            thread = threading.Thread(
                target=process_chat_model_input_augmentation,
                args=(task_data,),  # Fixed: pass task_data as a tuple
                daemon=True
            )

            thread.start()
        else:
            process_chat_model_request(task_data)


def process_chat_model_response(task_data: dict):
    agent_name = task_data["agent_name"]
    response = task_data["response"]
    meta_data = task_data.get("meta_data", {})

    if contains_mcp_command(agent_name, response):
        immediate_response = escape_system_text_with_command_escape_text(response)

        # Chat back that we are still processing
        enqueue_output_action(agent_name, immediate_response, meta_data)

        # Generate the new prompt with command results
        initial_prompt = meta_data.get("initial_prompt", "")
        next_prompt = process_mcp_commands(agent_name, response, initial_prompt)

        # Check for recustion
        DEFAULT_MAX_RECURSION_DEPTH = 3 # Allow initial call + 2 rounds of MCP commands
        chat_model_config = get_chat_model_config(agent_name)
        max_recusion_depth = chat_model_config.get("max_recusion_depth", DEFAULT_MAX_RECURSION_DEPTH)
        recursion_depth = meta_data.get("recursion_depth", 0)
        recursion_depth = recursion_depth + 1
        meta_data["recursion_depth"] = recursion_depth

        if recursion_depth >= max_recusion_depth:
            print(f"Max recursion depth ({max_recusion_depth}) reached for query: {response[:50]}...")
            error_response = "Max recursion depth ({max_recusion_depth}) reached for with response: \n" + response
            enqueue_output_action(agent_name, error_response, meta_data)
        else:
            task_data["prompt"] = next_prompt
            process_chat_model_request(task_data)
    else:
        # Load Output
        enqueue_output_action(agent_name, response, meta_data)

def process_output_action(task_data: dict):
    agent_name = task_data["agent_name"]
    chat_model_response = task_data["response"]
    meta_data = task_data.get("meta_data", {})

    output_action_config = get_output_action_config(agent_name)

    if output_action_config:
        python_code_module = output_action_config["python_code_module"]
        module = get_python_code_module(python_code_module)

        # Start the thread on the default handler
        thread = threading.Thread(
            target=module.process_output_action,
            args=(agent_name, chat_model_response, meta_data),
            daemon=True
        )
        
        thread.start() 


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
