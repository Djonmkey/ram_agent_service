### Starting the Service (Default)

```bash
# Make sure your Python virtual environment is activated
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Run the main Python script
python main.py
```

This will:
1. Start the Python backend

# RAM Agent Service (RAS)
RAM Agent Service (RAS) is an agentic platform developed by RAM Software for orchestrating and executing autonomous AI agents that integrate deeply with business systems and workflows. RAS supports the Model Context Protocol (MCP) to manage structured inputs and actions, utilizes RAG (Retrieval-Augmented Generation) for dynamic, real-time knowledge access, and enables scalable inference pipelines for context-aware decision-making. Designed for modularity and control, RAS empowers teams to build and manage intelligent agents that adapt to complex environments and deliver high-leverage automation.

## Overview

**RAM Agent Service (RAS)** is an agentic platform developed by **RAM Software** for orchestrating and executing **autonomous AI agents** that integrate seamlessly with business systems and workflows.

Built for **modularity** and **operational control**, RAS empowers teams to deploy intelligent agents capable of adapting to complex environments and delivering high-leverage automation.

---

## ✨ Key Features

- **🔌 Model Context Protocol (MCP)**
  - Structured communication between agents and tools
  - Manages contextual input/output and defined agent actions

- **📚 Retrieval-Augmented Generation (RAG)**
  - Real-time knowledge access from external sources
  - Improves relevance and decision-making in dynamic environments

- **⚙️ Scalable Inference Pipelines**
  - Efficient execution of AI workloads across agents
  - Maintains traceability and context awareness

---

## 🧠 Agent Architecture

All agents are defined in: config/agent_manifest.json

Each agent is composed of the following modular components:

| Component             | Description                                                                 |
|-----------------------|-----------------------------------------------------------------------------|
| `Input Trigger`       | Initiates the agent (e.g. webhook, scheduler, command)                      |
| `Chat Model`          | The core LLM used for reasoning and output generation                       |
| `Output Action`       | Defines how results are delivered (e.g. message, file, API call)            |
| `Memory` (opt.)       | Stores contextual state or historical data                                  |
| `Tools & Data` (opt.) | Allows use of external APIs, MCP commands, or RAG-enhanced data access      |

---

## 🧩 Design Principles

- **Modularity** – Components can be swapped or extended with minimal friction
- **Agentic Behavior** – Agents reason and act autonomously within defined scopes
- **Observability** – Detailed logging and diagnostics for transparency and debugging
- **Control** – Secure, declarative control over agent execution paths

## Prerequisites

- Python 3.12

## Installation

### Set up Python Environment

It's recommended to use a virtual environment for Python dependencies:

```bash
# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

## Development

The application structure is organized as follows:

- `main.py`: Main entry point
- `../../config/`: Configuration settings
- `../input_triggers/`: Dynamically loaded code modules for initiating an Agent i.e. Discord, Gmail-Email Received, File Created, etc.
- `../chat_models/`: Dynamically loaded code modules for communicating with an LLM i.e. OpenAI, Anthropic, Google, etc.
- `../memory/`: Dynamically loaded code modules for recording interactions and feeding history back to a given model.
- `../tools_and_data/`: Dynamically loaded code modules for interacting with MCP, OpenAPI or similar servers.
