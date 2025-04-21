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
from typing import Callable


# Global thread-safe work queues
chat_model_queue: queue.Queue[str] = queue.Queue()
input_trigger_queue: queue.Queue[str] = queue.Queue()
output_action_queue: queue.Queue[str] = queue.Queue()
tools_and_data_queue: queue.Queue[str] = queue.Queue()


def enqueue_chat_model(agent_name: str, contents: str) -> None:
    """
    Enqueue work for the chat model queue.

    :param agent_name: Name of the agent submitting the task
    :param contents: A JSON string describing the task
    """
    chat_model_queue.put(contents)


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


def _load_and_execute_module(module_path: str, function_name: str, task_data: dict) -> None:
    """
    Dynamically load a Python module and execute a function within it.

    :param module_path: Dot-separated path to the Python module (e.g., "my_package.my_module")
    :param function_name: Function to invoke within the module
    :param task_data: Dictionary of task input parameters
    """
    try:
        module = importlib.import_module(module_path)
        func: Callable = getattr(module, function_name)
        thread = threading.Thread(target=func, args=(task_data,), daemon=True)
        thread.start()
    except Exception as e:
        print(f"[ERROR] Failed to execute {module_path}.{function_name}: {e}")


def _start_queue_worker(name: str, task_queue: queue.Queue[str]) -> None:
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
                module_path = task["module"]
                function_name = task["function"]
                _load_and_execute_module(module_path, function_name, task)
            except Exception as e:
                print(f"[ERROR] {name} queue processing failed: {e}")

    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()


def start_all_queue_workers() -> None:
    """
    Start background worker threads for each queue.
    """
    _start_queue_worker("ChatModel", chat_model_queue)
    _start_queue_worker("InputTrigger", input_trigger_queue)
    _start_queue_worker("OutputAction", output_action_queue)
    _start_queue_worker("ToolsAndData", tools_and_data_queue)
