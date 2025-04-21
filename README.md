# ram_agent_service
RAM Agent Service (RAS) is an agentic platform developed by RAM Software for orchestrating and executing autonomous AI agents that integrate deeply with business systems and workflows. RAS supports the Model Context Protocol (MCP) to manage structured inputs and actions, utilizes RAG (Retrieval-Augmented Generation) for dynamic, real-time knowledge access, and enables scalable inference pipelines for context-aware decision-making. Designed for modularity and control, RAS empowers teams to build and manage intelligent agents that adapt to complex environments and deliver high-leverage automation.

## Development Setup

Follow these steps to set up your local development environment.

**Prerequisites:**

*   **Python 3.12:** This project requires Python version 3.12.x. You can download it from [python.org](https://www.python.org/downloads/).
    *   *Note:* Python 3.13 is currently **not** compatible due to dependency issues. Please ensure you are using a 3.12 release.
*   **pip:** Python's package installer (usually comes with Python).

**Steps:**

1.  **Clone the Repository (if you haven't already):**
    ```bash
    git clone <your-repository-url>
    cd ram_agent_service
    ```

2.  **Create a Virtual Environment:**
    It's highly recommended to use a virtual environment to isolate project dependencies. Navigate to the project root directory (`ram_agent_service/`) in your terminal and run:
    ```bash
    python3.12 -m venv .venv
    ```
    *(Use `python` or the specific command for your Python 3.12 installation if `python3.12` isn't directly available)*

3.  **Activate the Virtual Environment:**
    *   **macOS / Linux:**
        ```bash
        source .venv/bin/activate
        ```
    *   **Windows (Git Bash):**
        ```bash
        source .venv/Scripts/activate
        ```
    *   **Windows (Command Prompt):**
        ```bash
        .venv\Scripts\activate.bat
        ```
    *   **Windows (PowerShell):**
        ```bash
        .venv\Scripts\Activate.ps1
        ```
    Your terminal prompt should change to indicate the environment is active (e.g., `(.venv) your-user@host:...`).

4.  **Install Dependencies:**
    Install the required packages from the `requirements.txt` file located in the `src/ras/` directory:
    ```bash
    pip install -r src/ras/requirements.txt
    ```

5.  **Ready to Go!**
    Your environment is now set up. You can run and debug the application (e.g., `python src/ras/main.py` or however your application is started). Remember to activate the virtual environment (`source .venv/bin/activate` or equivalent) in each new terminal session before working on the project.

