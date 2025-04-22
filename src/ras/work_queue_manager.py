"""
work_queue_manager.py

This module provides global thread-safe queues for managing asynchronous work
across different components of a configuration-driven agent system. Each queue
represents a functional domain (e.g., chat model, input trigger) and supports
threaded execution of dynamically loaded Python modules on FIFO dequeued tasks.

Author: David McKee
"""

import threading
import queue
import json
import importlib

from typing import Callable, Dict, Any


# Global thread-safe work queues
chat_model_queue: queue.Queue[str] = queue.Queue()
input_trigger_queue: queue.Queue[str] = queue.Queue()
output_action_queue: queue.Queue[str] = queue.Queue()
tools_and_data_queue: queue.Queue[str] = queue.Queue()

QUEUE_NAME_CHAT_MODEL = "ChatModel"
QUEUE_NAME_INPUT_TRIGGER = "InputTrigger"
QUEUE_NAME_OUTPUT_ACTION = "OutputAction"
QUEUE_NAME_TOOLS_AND_DATA = "ToolsAndData"


def enqueue_chat_model(agent_name: str, contents: Dict[str, Any]) -> None:
    """
    Enqueue work for the chat model queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    contents["agent_name"] = agent_name

    json_string = json.dumps(contents)
    
    chat_model_queue.put(json_string)


def enqueue_input_trigger(agent_name: str, contents: str) -> None:
    """
    Enqueue work for the input trigger queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    input_trigger_queue.put(contents)


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

def process_input_trigger(task_data: dict):
    # TODO: CHECK FOR INPUT AUGMENTATION

    # Load chat model on new thread and execute.
    module = importlib.import_module(module_path)
    func: Callable = getattr(module, function_name)
    thread = threading.Thread(target=func, args=(task_data,), daemon=True)
    thread.start()

def process_chat_model(task_data: dict):
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
        

        if queue_name == QUEUE_NAME_CHAT_MODEL:
           process_chat_model(task_data)

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
    _start_queue_worker(QUEUE_NAME_CHAT_MODEL, chat_model_queue)
    _start_queue_worker(QUEUE_NAME_INPUT_TRIGGER, input_trigger_queue)
    _start_queue_worker("OutputAction", output_action_queue)
    _start_queue_worker("ToolsAndData", tools_and_data_queue)
