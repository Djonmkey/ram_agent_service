### Starting with the UI (Default)

To start the application with the Electron UI:

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
2. Launch the Electron UI
3. Open the application in your default web browser


# Executive Assistant

A Python-based application designed to help manage time spent on various categorized activities. The application features both a command-line interface and an Electron-based graphical user interface.

## Overview

Executive Assistant helps you track and manage your time across different activities and categories. It provides:

- Activity tracking with timers
- Category-based time allocation
- Statistics and reporting
- AI-assisted planning via LLM integration
- MCP (Model Context Protocol) tool integration

## Prerequisites

- Python 3.8 or higher
- Node.js 16 or higher (for the UI)
- npm (Node Package Manager)

## Installation

### 1. Set up Python Environment

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

### 2. Install Python Dependencies

With the virtual environment activated, install the required Python packages:

```bash
# Install required packages (requirements.txt not included in repo yet)
# pip install -r requirements.txt

# For now, you may need to install these packages manually:
pip install flask requests python-dateutil
```

### 3. Install UI Dependencies

The UI is built with Electron and requires Node.js dependencies:

```bash
# Navigate to the UI directory
cd ui

# Install Node.js dependencies
npm install
```

## Running the Application

### CLI Mode

To run the application in CLI mode without the UI:

```bash
# Make sure your Python virtual environment is activated
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Run with the CLI flag
python main.py --cli
```

### Command-line Options

The application supports the following command-line options:

- `--cli`: Run in CLI mode without UI
- `--stats`: Display time stats and exit

Example:
```bash
# Show stats and exit
python main.py --stats
```

## Basic Usage

### CLI Commands

When running in CLI mode, the following commands are available:

- `stats`: Display time statistics
- `activities`: List all activities
- `start <activity_id> <duration_minutes>`: Start an activity
- `end`: End the current activity
- `chat <message>`: Chat with the AI assistant
- `exit/quit`: Exit the application

### UI

The Electron UI provides a more user-friendly interface for managing activities and viewing statistics. The UI automatically connects to the Python backend when launched.

## Development

The application structure is organized as follows:

- `main.py`: Main entry point
- `backend/`: Backend Python modules
- `config/`: Configuration settings
- `data/`: Data storage
- `ui/`: Electron UI

## License

MIT
