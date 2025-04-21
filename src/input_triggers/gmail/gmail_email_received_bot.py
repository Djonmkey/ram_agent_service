# src/input_triggers/gmail/gmail_email_received_bot.py
import asyncio
import base64
import time
import os
import logging
from typing import Optional, Dict, Any, List

# Google API Client Libraries
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Ensure src is in path for sibling imports
import sys
from pathlib import Path
SRC_DIR = Path(__file__).resolve().parent.parent.parent # Go up three levels: gmail -> input_triggers -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from input_triggers.input_triggers import InputTrigger

# --- Constants ---
# Scopes required for reading emails and modifying them (e.g., marking as read)
SCOPES = ['https://www.googleapis.com/auth/gmail.modify']
# Default path for token file relative to project root (can be overridden in trigger config)
DEFAULT_TOKEN_PATH = "secrets/gmail_token.json"
# Default path for credentials file relative to project root (can be overridden in trigger config)
DEFAULT_CREDENTIALS_PATH = "secrets/gmail_credentials.json"
# Default polling interval (can be overridden in trigger config)
DEFAULT_POLLING_INTERVAL_SECONDS = 60

class GmailEmailReceivedBot(InputTrigger):
    """
    An input trigger that monitors a Gmail inbox for new emails matching
    specific criteria and processes them using an AI agent.
    """

    def __init__(self,
                 agent_name: str,
                 trigger_config_data: Optional[Dict[str, Any]] = None,
                 trigger_secrets: Optional[Dict[str, Any]] = None):
        """
        Initializes the GmailEmailReceivedBot.

        Args:
            agent_name: The name of the agent this trigger instance belongs to.
            trigger_config_data: Dictionary containing configuration for this trigger.
                                 Expected keys:
                                 - 'polling_interval_seconds' (optional, defaults to 60)
                                 - 'gmail_query' (optional, defaults to 'is:unread')
                                 - 'mark_as_read' (optional, boolean, defaults to True)
                                 - 'token_path' (optional, relative to project root, defaults to secrets/gmail_token.json)
                                 - 'credentials_path' (optional, relative to project root, defaults to secrets/gmail_credentials.json)
            trigger_secrets: Dictionary containing secrets (not directly used by this trigger,
                             but passed for consistency and potential future use).
        """
        super().__init__(agent_name, trigger_config_data, trigger_secrets)
        self.logger = logging.getLogger(f"{self.agent_name}.{self.name}") # Use specific logger
        self.service = None
        self.credentials = None
        self._stop_event = asyncio.Event()
        self.polling_interval = self.trigger_config.get('polling_interval_seconds', DEFAULT_POLLING_INTERVAL_SECONDS)
        self.gmail_query = self.trigger_config.get('gmail_query', 'is:unread') # Default to unread emails
        self.mark_as_read = self.trigger_config.get('mark_as_read', True)

        # Resolve paths relative to PROJECT_ROOT (assuming it's defined appropriately)
        # If PROJECT_ROOT isn't easily available here, consider passing absolute paths
        # in the config or resolving them during the loading phase in input_triggers_main.py
        # For now, assume paths in config are relative to where the app runs or are absolute.
        # A robust solution might involve passing PROJECT_ROOT during init or resolving earlier.
        # Let's assume PROJECT_ROOT is accessible for demonstration:
        try:
            # This assumes PROJECT_ROOT is defined somewhere accessible, like in input_triggers_main
            # If not, these paths need to be absolute or resolved differently.
            from input_triggers.input_triggers_main import PROJECT_ROOT
            self.token_path = PROJECT_ROOT / self.trigger_config.get('token_path', DEFAULT_TOKEN_PATH)
            self.credentials_path = PROJECT_ROOT / self.trigger_config.get('credentials_path', DEFAULT_CREDENTIALS_PATH)
        except ImportError:
             self.logger.warning("Could not import PROJECT_ROOT. Assuming paths in config are absolute or relative to cwd.")
             # Fallback: treat paths as potentially relative to current working directory or absolute
             self.token_path = Path(self.trigger_config.get('token_path', DEFAULT_TOKEN_PATH))
             self.credentials_path = Path(self.trigger_config.get('credentials_path', DEFAULT_CREDENTIALS_PATH))


        self.logger.info(f"Gmail Bot configured for Agent '{self.agent_name}'")
        self.logger.info(f"  Polling Interval: {self.polling_interval}s")
        self.logger.info(f"  Gmail Query: '{self.gmail_query}'")
        self.logger.info(f"  Mark as Read: {self.mark_as_read}")
        self.logger.info(f"  Token Path: {self.token_path}")
        self.logger.info(f"  Credentials Path: {self.credentials_path}")


    @property
    def name(self) -> str:
        return "GmailEmailReceivedBot"

    async def initialize(self):
        """Initializes the Gmail API service."""
        await super().initialize() # Call base class initialize
        self.logger.info("Initializing Gmail API service...")
        try:
            self.credentials = self._get_credentials()
            if not self.credentials:
                self.logger.error("Failed to obtain valid credentials.")
                # Decide how to handle this - raise error, prevent start?
                # For now, log error; start() will likely fail.
                return
            self.service = build('gmail', 'v1', credentials=self.credentials)
            self.logger.info("Gmail API service initialized successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing Gmail service: {e}", exc_info=True)
            # Prevent starting if initialization fails critically
            raise RuntimeError(f"Failed to initialize Gmail service: {e}")


    def _get_credentials(self) -> Optional[Credentials]:
        """Gets valid user credentials from storage or initiates OAuth2 flow."""
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first time.
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
                self.logger.info(f"Loaded credentials from {self.token_path}")
            except Exception as e:
                self.logger.warning(f"Could not load credentials from {self.token_path}: {e}. Will attempt refresh or re-auth.")
                creds = None # Ensure creds is None if loading failed

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self.logger.info("Credentials expired. Refreshing token...")
                try:
                    creds.refresh(Request())
                    self.logger.info("Token refreshed successfully.")
                except Exception as e:
                    self.logger.error(f"Failed to refresh token: {e}. Need to re-authenticate.", exc_info=True)
                    creds = None # Force re-authentication
            else:
                self.logger.info("No valid credentials found. Starting OAuth flow...")
                if not self.credentials_path.exists():
                     self.logger.error(f"Credentials file not found at {self.credentials_path}. Cannot initiate OAuth flow.")
                     return None
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(self.credentials_path), SCOPES)
                    # TODO: Consider how to handle the console-based flow in a service context.
                    # This might require a one-time setup script or a web-based flow.
                    # For now, assuming console interaction is possible during setup/first run.
                    creds = flow.run_local_server(port=0) # Or flow.run_console()
                    self.logger.info("OAuth flow completed successfully.")
                except Exception as e:
                    self.logger.error(f"Error during OAuth flow: {e}", exc_info=True)
                    return None # Failed to get credentials

            # Save the credentials for the next run
            if creds:
                try:
                    # Ensure the directory exists
                    self.token_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.token_path, 'w') as token_file:
                        token_file.write(creds.to_json())
                    self.logger.info(f"Credentials saved to {self.token_path}")
                except Exception as e:
                    self.logger.error(f"Failed to save credentials to {self.token_path}: {e}", exc_info=True)

        return creds

    async def _check_emails(self):
        """Checks for new emails matching the criteria."""
        if not self.service:
            self.logger.error("Gmail service not available. Cannot check emails.")
            return

        self.logger.debug(f"Checking for emails matching query: '{self.gmail_query}'")
        try:
            # List emails matching the query
            results = self.service.users().messages().list(userId='me', q=self.gmail_query).execute()
            messages = results.get('messages', [])

            if not messages:
                self.logger.debug("No new messages found matching criteria.")
                return

            self.logger.info(f"Found {len(messages)} new message(s). Processing...")

            for msg_summary in messages:
                msg_id = msg_summary['id']
                try:
                    # Get the full message details
                    msg = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute() # Use 'full' or 'metadata' as needed
                    payload = msg.get('payload', {})
                    headers = payload.get('headers', [])

                    # Extract relevant information (Subject, From, Snippet, Body)
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                    sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
                    snippet = msg.get('snippet', 'No Snippet')
                    body = self._get_email_body(payload) # Decode body

                    self.logger.info(f"Processing email: ID={msg_id}, From='{sender}', Subject='{subject}'")
                    self.logger.debug(f"  Snippet: {snippet}")
                    # Avoid logging full body unless necessary for debugging
                    # self.logger.debug(f"  Body: {body[:200]}...") # Log first 200 chars

                    # Construct the initial query/prompt for the AI agent
                    # Customize this prompt as needed
                    initial_query = (
                        f"Received a new email:\n"
                        f"From: {sender}\n"
                        f"Subject: {subject}\n"
                        f"Snippet: {snippet}\n\n"
                        f"Body:\n{body}\n\n"
                        f"Please process this email content."
                    )

                    # Define the callback function to handle the AI's final response
                    def create_callback(email_id, email_subject):
                        def email_response_callback(ai_response: str):
                            self.logger.info(f"AI processing finished for email ID {email_id} ('{email_subject}').")
                            self.logger.debug(f"AI Response for {email_id}: {ai_response}")
                            # Potentially take action based on AI response (e.g., reply, label)
                            # This part is application-specific and not implemented here.
                        return email_response_callback

                    # Execute the AI agent asynchronously
                    self._execute_ai_agent_async(
                        initial_query=initial_query,
                        callback=create_callback(msg_id, subject)
                    )

                    # Mark the email as read (if configured)
                    if self.mark_as_read:
                        self.logger.debug(f"Marking email {msg_id} as read.")
                        self.service.users().messages().modify(
                            userId='me',
                            id=msg_id,
                            body={'removeLabelIds': ['UNREAD']}
                        ).execute()

                except HttpError as error:
                    self.logger.error(f"An HTTP error occurred processing message ID {msg_id}: {error}", exc_info=True)
                except Exception as e:
                    self.logger.error(f"An unexpected error occurred processing message ID {msg_id}: {e}", exc_info=True)

        except HttpError as error:
            self.logger.error(f"An HTTP error occurred while listing emails: {error}", exc_info=True)
            # Handle specific errors like auth failures
            if error.resp.status == 401:
                 self.logger.error("Authentication error. Credentials might be invalid or revoked.")
                 # Consider attempting to refresh credentials or stopping the trigger
                 self.credentials = None # Force re-auth attempt on next cycle if possible
        except Exception as e:
            self.logger.error(f"An unexpected error occurred while checking emails: {e}", exc_info=True)


    def _get_email_body(self, payload: Dict[str, Any]) -> str:
        """Extracts and decodes the email body from the payload."""
        body = ""
        if 'parts' in payload:
            # Handle multipart emails (common case)
            for part in payload['parts']:
                mime_type = part.get('mimeType', '')
                if mime_type == 'text/plain':
                    data = part.get('body', {}).get('data')
                    if data:
                        body += base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                        break # Often, the first text/plain part is sufficient
                elif mime_type == 'text/html':
                    # Optionally handle HTML body if plain text is not found
                    # For simplicity, we prioritize plain text here
                    pass
                elif 'parts' in part: # Recursively check nested parts
                    nested_body = self._get_email_body(part)
                    if nested_body: # Prefer plain text from nested parts if found
                         if part.get('mimeType', '') == 'text/plain':
                              body = nested_body
                              break
                         elif not body: # Use nested body if no plain text found yet
                              body = nested_body

        elif 'body' in payload:
            # Handle single part emails
            data = payload.get('body', {}).get('data')
            mime_type = payload.get('mimeType', '')
            if data and mime_type == 'text/plain':
                body = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
            # Add handling for single part HTML if needed

        return body.strip() if body else "No text body found."


    async def start(self):
        """Starts the email checking loop."""
        await super().start() # Log start message
        if not self.service:
             self.logger.error("Cannot start polling: Gmail service not initialized.")
             # Optionally raise an error or simply return to prevent running
             raise RuntimeError("Gmail service failed to initialize. Cannot start trigger.")

        self._stop_event.clear()
        self.logger.info(f"Starting email polling every {self.polling_interval} seconds...")
        while not self._stop_event.is_set():
            try:
                await self._check_emails()
                # Wait for the polling interval or until stop is requested
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.polling_interval)
            except asyncio.TimeoutError:
                # This is expected, just means the interval passed
                continue
            except Exception as e:
                self.logger.error(f"Unexpected error in polling loop: {e}", exc_info=True)
                # Avoid rapid failure loops, wait before retrying
                await asyncio.sleep(self.polling_interval)


    async def stop(self):
        """Stops the email checking loop."""
        await super().stop() # Log stop message
        self.logger.info("Stopping email polling...")
        self._stop_event.set()
        # No external connections to explicitly close here, service object handles its state.
        self.logger.info("GmailEmailReceivedBot stopped.")

