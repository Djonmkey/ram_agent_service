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
import asyncio

from typing import Callable, Dict, Any
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent.parent  # Go up three levels: discord -> input_triggers -> src
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

    # Check if there's a callback in meta_data and call it
    callback = meta_data.get("callback")
    if callback and callable(callback):
        try:
            callback(agent_name, response, meta_data)
        except Exception as e:
            print(f"Error calling callback: {e}")
            # Remove callback from meta_data before enqueuing to avoid JSON serialization issues
            meta_data = {k: v for k, v in meta_data.items() if k != "callback"}
    else:
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
    module_path = python_code_module.replace("/", ".")  # Unix-style path to dot notation
    module_path = module_path.replace("\\", ".")  # Windows-style path to dot notation

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


def process_chat_model_request(task_data: dict, callback: Callable = None):
    agent_name = task_data["agent_name"]
    prompt = task_data["prompt"]
    meta_data = task_data.get("meta_data", {})

    chat_model_config = get_chat_model_config(agent_name)
    python_code_module = chat_model_config["python_code_module"]

    # Import the module dynamically
    module = get_python_code_module(python_code_module)

    if callback is not None:
        # Create a wrapper function that calls the original ask_chat_model and then the callback
        def ask_chat_model_with_callback(agent_name, prompt, meta_data):
            # Store callback in meta_data temporarily for the chat model to use
            meta_data["callback"] = callback
            module.ask_chat_model(agent_name, prompt, meta_data)

        # Start the thread with the wrapper
        thread = threading.Thread(
            target=ask_chat_model_with_callback,
            args=(agent_name, prompt, meta_data),
            daemon=True
        )
    else:
        # Start the thread normally
        thread = threading.Thread(
            target=module.ask_chat_model,
            args=(agent_name, prompt, meta_data),
            daemon=True
        )

    thread.start()


def process_input_trigger(task_data: dict, mcp_client_manager=None):
    agent_name = task_data["agent_name"]
    prompt = task_data["prompt"]
    meta_data = task_data.get("meta_data", {})

    # Step 1: Check for a specific MCP Client
    tools_and_data_mcp_commands_config = get_tools_and_data_mcp_commands_config(agent_name)
    mcp_client_python_code_module = tools_and_data_mcp_commands_config.get("mcp_client_python_code_module")

    if mcp_client_python_code_module:
        # Here I want to retreive the appropraite mcp_client by agent_name
        mcp_client = mcp_client_manager.get_client(agent_name)
        if mcp_client:
            mcp_client.process_query(agent_name, prompt, meta_data)
        else:
            print(f"No MCPClient found for agent: {agent_name}")
    
    else:
        # Step 1: Execute Input Augmentation
        input_augmentation_config = get_input_augmentation_config(agent_name)

        if input_augmentation_config:
            # Start the thread
            thread = threading.Thread(
                target=process_chat_model_input_augmentation,
                args=(agent_name, prompt, meta_data),
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
        immediate_response = escape_system_text_with_command_escape_text(agent_name, response)

        # Chat back that we are still processing
        enqueue_output_action(agent_name, immediate_response, meta_data)

        # Generate the new prompt with command results
        initial_prompt = meta_data.get("initial_prompt", "")
        next_prompt = process_mcp_commands(agent_name, response, initial_prompt)

        # Check for recustion
        DEFAULT_MAX_RECURSION_DEPTH = 3  # Allow initial call + 2 rounds of MCP commands
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


def _load_and_execute_module(queue_name: str, task_data: dict, mcp_client_manager) -> None:
    """
    Dynamically load a Python module and execute a function within it.

    :param module_path: Dot-separated path to the Python module (e.g., "my_package.my_module")
    :param function_name: Function to invoke within the module
    :param task_data: Dictionary of task input parameters
    """
    try:
        if queue_name == QUEUE_NAME_CHAT_MODEL_REQUEST:
            def chat_model_callback(agent_name: str, response: str, meta_data: dict):
                enqueue_chat_model_response(agent_name, response, meta_data)

            process_chat_model_request(task_data, callback=chat_model_callback)

        if queue_name == QUEUE_NAME_CHAT_MODEL_RESPONSE:
            process_chat_model_response(task_data)

        if queue_name == QUEUE_NAME_INPUT_TRIGGER:
            process_input_trigger(task_data, mcp_client_manager)

        if queue_name == QUEUE_NAME_OUTPUT_ACTION:
            process_output_action(task_data)

    except Exception as e:
        print(f"[ERROR] Failed to process {queue_name}.: {e}")


def _start_queue_worker(queue_name: str, task_queue: queue.Queue[str], mcp_client_manager) -> None:
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
                _load_and_execute_module(queue_name, task, mcp_client_manager)
            except Exception as e:
                print(f"[ERROR] {queue_name} queue processing failed: {e}")

    thread = threading.Thread(target=worker_loop, daemon=True)
    thread.start()


class WorkQueueManager:
    def __init__(self, mcp_client_manager):
        self.mcp_client_manager = mcp_client_manager
        self.input_queue = asyncio.Queue()
        self.agent_queues = {}  # Agent-specific queues
        self.agent_tasks = {}  # Track agent tasks
        self.agent_shutdown_flags = {}  # Track shutdown flags for each agent
        self.all_agents_shutdown_event = asyncio.Event()  # Global shutdown event
        self.queue_manager_thread = None
        self.queue_manager_thread_lock = threading.Lock()
        self.is_running = False

    def start(self):
        with self.queue_manager_thread_lock:
            if self.is_running:
                return  # Prevent starting multiple times
            self.is_running = True
            self.queue_manager_thread = threading.Thread(target=self._run, daemon=True)
            self.queue_manager_thread.start()

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._process_input_queue())
        finally:
            loop.close()

    async def _process_input_queue(self):
        while True:
            try:
                agent_name, prompt = await self.input_queue.get()
                asyncio.create_task(self._process_input_trigger(agent_name, prompt))
                self.input_queue.task_done()
            except asyncio.CancelledError:
                break  # Exit loop if cancelled
            except Exception as e:
                print(f"Error processing input queue: {e}")

    async def _process_input_trigger(self, agent_name: str, prompt: str):
        try:
            # Get the agent-specific queue, creating it if it doesn't exist
            if agent_name not in self.agent_queues:
                self.agent_queues[agent_name] = asyncio.Queue()
                self.agent_shutdown_flags[agent_name] = asyncio.Event()  # Initialize shutdown flag
                asyncio.create_task(self._agent_worker(agent_name))  # Start agent worker

            # Enqueue the prompt to the agent-specific queue
            await self.agent_queues[agent_name].put(prompt)
        except Exception as e:
            print(f"Error enqueuing prompt for agent {agent_name}: {e}")

    async def _agent_worker(self, agent_name: str):
        try:
            while not self.agent_shutdown_flags[agent_name].is_set():
                try:
                    prompt = await asyncio.wait_for(self.agent_queues[agent_name].get(), timeout=1)  # Check every 1 second
                    await self._execute_agent_task(agent_name, prompt)
                    self.agent_queues[agent_name].task_done()
                except asyncio.TimeoutError:
                    continue  # No new prompt, check shutdown flag
                except Exception as e:
                    print(f"Error in agent worker for {agent_name}: {e}")
        finally:
            print(f"Agent worker shutting down: {agent_name}")

    async def _execute_agent_task(self, agent_name: str, prompt: str):
        try:
            # Load agent config
            tools_and_data_mcp_commands_config = get_tools_and_data_mcp_commands_config(agent_name)
            mcp_client_python_code_module = tools_and_data_mcp_commands_config.get("mcp_client_python_code_module")

            if mcp_client_python_code_module:
                # Load MCPClient class and execute
                mcp_client = self.mcp_client_manager.get_client(agent_name)
                if mcp_client:
                    mcp_client.process_query(prompt)
                else:
                    print(f"No MCPClient found for agent: {agent_name}")
            else:
                # Execute Input Augmentation
                input_augmentation_config = get_input_augmentation_config(agent_name)

                if input_augmentation_config:
                    # Start the thread
                    thread = threading.Thread(
                        target=process_chat_model_input_augmentation,
                        args=(agent_name, prompt, {}),
                        daemon=True
                    )

                    thread.start()
                else:
                    # process_chat_model_request(task_data)
                    print("No MCP client or input augmentation configured")

        except Exception as e:
            print(f"Error executing agent task for {agent_name}: {e}")

    def shutdown(self):
        """
        Signal all agent workers to stop and wait for them to finish.
        """
        print("Signaling shutdown to all agent workers...")
        for agent_name in self.agent_shutdown_flags:
            self.agent_shutdown_flags[agent_name].set()  # Signal shutdown
        print("Waiting for queue manager thread to finish...")
        if self.queue_manager_thread:
            self.queue_manager_thread.join(timeout=10)  # Wait for thread to finish
            if self.queue_manager_thread.is_alive():
                print("Warning: Queue manager thread did not exit cleanly.")
        print("Shutdown complete.")


def get_tools_and_data_mcp_commands_config(agent_name: str) -> Dict[str, Any]:
    """
    Get the tools and data MCP commands configuration for the given agent name.

    :param agent_name: Name of the agent
    :return: The tools and data MCP commands configuration
    """
    # TODO: Implement this function
    return {}


def start_all_queue_workers(mcp_client_manager) -> None:
    """
    Start background worker threads for each queue.
    """
    _start_queue_worker(QUEUE_NAME_CHAT_MODEL_REQUEST, chat_model_request_queue, mcp_client_manager)
    _start_queue_worker(QUEUE_NAME_CHAT_MODEL_RESPONSE, chat_model_response_queue, mcp_client_manager)
    _start_queue_worker(QUEUE_NAME_INPUT_TRIGGER, input_trigger_queue, mcp_client_manager)
    _start_queue_worker(QUEUE_NAME_OUTPUT_ACTION, output_action_queue, mcp_client_manager)
