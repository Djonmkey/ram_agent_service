# src/input_triggers/gmail/gmail_email_received_bot.py
import os
import time
import json
import base64
import asyncio
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

SRC_DIR = (
    Path(__file__).resolve().parent.parent.parent
)  # Go up three levels: gmail -> input_triggers -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from input_triggers.input_triggers import InputTrigger

# --- Constants ---
# Scopes required for reading emails and modifying them (e.g., marking as read)
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
# Default path for token file relative to project root (can be overridden in trigger config)
DEFAULT_TOKEN_PATH = "secrets/gmail_token.json"
# Default path for credentials file relative to project root (can be overridden in trigger config)
DEFAULT_CREDENTIALS_PATH = "secrets/gmail_credentials.json"
# Default polling interval (can be overridden in trigger config)
DEFAULT_POLLING_INTERVAL_SECONDS = 60

def perform_oauth_flow(
        client_secrets_path: Path,
        scopes: List[str],
        logger: Optional[logging.Logger] = None,
    ) -> Optional[Credentials]:
    """
    Executes the OAuth authorization flow using the specified client secrets file and scopes.

    Args:
        client_secrets_path (Path): Path to the OAuth 2.0 client secrets JSON file.
        scopes (List[str]): List of OAuth scopes to request.
        logger (Optional[logging.Logger]): Logger instance for logging messages.

    Returns:
        Optional[Credentials]: The authorized credentials object if successful, otherwise None.
    """
    try:
        if not client_secrets_path.exists():
            if logger:
                logger.error(f"Client secrets file not found: {client_secrets_path}")
            return None

        flow = InstalledAppFlow.from_client_secrets_file(
            str(client_secrets_path),
            scopes=scopes
        )

        creds = flow.run_local_server(
            port=0,
            prompt='consent',
            authorization_prompt_message='Please authorize this app via your browser: {url}'
        )

        if logger:
            logger.info("OAuth flow completed successfully.")
        return creds

    except Exception as e:
        if logger:
            logger.error(f"Error during OAuth flow: {e}", exc_info=True)
        return None

class GmailEmailReceivedBot(InputTrigger):
    """
    An input trigger that monitors a Gmail inbox for new emails matching
    specific criteria and processes them using an AI agent.
    """

    def __init__(
        self,
        agent_config_data: Dict[str, Any],
        trigger_config_data: Optional[Dict[str, Any]] = None,
        trigger_secrets: Optional[Dict[str, Any]] = None,
    ):
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
        super().__init__(agent_config_data, trigger_config_data, trigger_secrets)

        self.logger = logging.getLogger(
            f"{self.agent_name}.{self.name}"
        )  # Use specific logger
        self.service = None
        self.credentials = None
        self._stop_event = asyncio.Event()
        self.polling_interval = trigger_config_data.get(
            "polling_interval_seconds", DEFAULT_POLLING_INTERVAL_SECONDS
        )
        self.gmail_query = trigger_config_data.get(
            "gmail_query", "is:unread"
        )  # Default to unread emails
        self.mark_as_read = trigger_config_data.get("mark_as_read", True)
        self.gmail_refresh_token = self.trigger_secrets.get("gmail_refresh_token")

        self.access_token_path = Path(
            trigger_config_data.get("access_token_path", DEFAULT_TOKEN_PATH)
        )

        self.logger.info(f"Gmail Bot configured for Agent '{self.agent_name}'")
        self.logger.info(f"  Polling Interval: {self.polling_interval}s")
        self.logger.info(f"  Gmail Query: '{self.gmail_query}'")
        self.logger.info(f"  Mark as Read: {self.mark_as_read}")
        self.logger.info(f"  Token Path: {self.access_token_path}")

    @property
    def name(self) -> str:
        return "GmailEmailReceivedBot"

    async def initialize(self):
        """Initializes the Gmail API service."""
        await super().initialize()  # Call base class initialize
        self.logger.info("Initializing Gmail API service...")
        try:
            self.service = self._authenticate_gmail_api()

            if self.service:
                self.logger.info("Gmail API service initialized successfully.")
            else:
                self.logger.error("Failed to initialize Gmail API service.")

        except Exception as e:
            self.logger.error(f"Error initializing Gmail service: {e}", exc_info=True)
            # Prevent starting if initialization fails critically
            raise RuntimeError(f"Failed to initialize Gmail service: {e}")
        
        
    def _authenticate_gmail_api(self):
        """
        Authenticates the user with Gmail API using OAuth2 and returns the Gmail service object.

        Handles token loading, refreshing, and the OAuth2 flow if necessary.

        Returns:
            Authorized Gmail service resource or None if authentication fails.
        """
        creds: Optional[Credentials] = None
        # Define project root based on SRC_DIR (assuming SRC_DIR is correctly defined)
        project_root = SRC_DIR.parent

        # --- Get paths from config, using self.trigger_config ---
        # Use .get with default values defined as constants
        access_token_rel_path = self.trigger_config.get("access_token_file", DEFAULT_TOKEN_PATH)
        client_secrets_rel_path = self.trigger_config.get("client_secrets_file", DEFAULT_CREDENTIALS_PATH)

        # --- Resolve absolute paths using pathlib ---
        access_token_abs_path = (project_root / access_token_rel_path).resolve()
        client_secrets_abs_path = (project_root / client_secrets_rel_path).resolve()

        self.logger.info(f"Attempting to load token from: {access_token_abs_path}")
        self.logger.info(f"Using client secrets file: {client_secrets_abs_path}")

        # --- Load existing credentials ---
        if access_token_abs_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(access_token_abs_path), SCOPES)
                self.logger.info("Loaded existing credentials from token file.")
            except Exception as e:
                self.logger.warning(f"Failed to load credentials from {access_token_abs_path}: {e}. Will attempt re-authentication.")
                creds = None # Ensure creds is None if loading fails

        # --- Validate credentials and refresh if necessary ---
        if creds and not creds.valid:
            self.logger.info("Existing credentials are not valid.")
            if creds.expired and creds.refresh_token:
                self.logger.info("Attempting to refresh token...")
                try:
                    # Use google.auth.transport.requests.Request for refreshing
                    from google.auth.transport.requests import Request
                    creds.refresh(Request())
                    self.logger.info("Token refreshed successfully.")
                except Exception as e:
                    self.logger.warning(f"Failed to refresh token: {e}. Proceeding with full re-authentication.")
                    creds = None # Force re-auth if refresh fails
            else:
                self.logger.info("Credentials invalid and cannot be refreshed. Proceeding with full re-authentication.")
                creds = None # Force re-auth

        # --- Perform OAuth flow if no valid credentials ---
        if not creds: # This covers None, invalid, or failed refresh
            self.logger.info("No valid credentials found. Starting OAuth flow...")
            if not client_secrets_abs_path.exists():
                self.logger.error(f"Client secrets file not found: {client_secrets_abs_path}. Cannot proceed with authentication.")
                return None # Critical error, cannot authenticate

            try:
                creds = perform_oauth_flow(client_secrets_abs_path, SCOPES, self.logger)
                self.logger.info("OAuth flow completed successfully.")
            except FileNotFoundError:
                # Should be caught by the exists() check above, but good defense
                self.logger.error(f"Client secrets file disappeared during flow creation: {client_secrets_abs_path}")
                return None
            except Exception as e:
                # Catch potential errors during run_local_server (e.g., port issues, user cancellation)
                self.logger.error(f"Error during OAuth authorization flow: {e}", exc_info=True)
                return None

        # --- Save the credentials (if newly obtained or refreshed) ---
        # Check if creds exist *and* if they are valid before saving
        if creds and creds.valid:
            try:
                # Ensure parent directory exists before writing
                access_token_abs_path.parent.mkdir(parents=True, exist_ok=True)
                with open(access_token_abs_path, 'w') as token:
                    token.write(creds.to_json())
                self.logger.info(f"Credentials saved to {access_token_abs_path}")
            except IOError as e:
                self.logger.error(f"Failed to save token file to {access_token_abs_path}: {e}")
            except Exception as e:
                self.logger.error(f"An unexpected error occurred while saving token: {e}")
        elif creds and not creds.valid:
            # This case might happen if refresh failed but we didn't nullify creds correctly earlier
            self.logger.warning("Credentials obtained but are invalid. Not saving token.")


        # --- Build and return the service ---
        if creds and creds.valid:
            try:
                service = build('gmail', 'v1', credentials=creds)
                self.logger.info("Gmail service built successfully.")
                return service
            except Exception as e:
                self.logger.error(f"Failed to build Gmail service with obtained credentials: {e}", exc_info=True)
                return None
        else:
            # This path is reached if creds are None initially and OAuth failed,
            # or if refresh failed and OAuth failed, or if creds became invalid somehow.
            self.logger.error("Failed to obtain valid credentials after all attempts.")
            return None

    async def _check_emails(self):
        """Checks for new emails matching the criteria."""
        if not self.service:
            self.logger.error("Gmail service not available. Cannot check emails.")
            return

        self.logger.debug(f"Checking for emails matching query: '{self.gmail_query}'")
        try:
            # List emails matching the query
            results = (
                self.service.users()
                .messages()
                .list(userId="me", q=self.gmail_query)
                .execute()
            )
            messages = results.get("messages", [])

            if not messages:
                self.logger.debug("No new messages found matching criteria.")
                return

            self.logger.info(f"Found {len(messages)} new message(s). Processing...")

            for msg_summary in messages:
                msg_id = msg_summary["id"]
                try:
                    # Get the full message details
                    msg = (
                        self.service.users()
                        .messages()
                        .get(userId="me", id=msg_id, format="full")
                        .execute()
                    )  # Use 'full' or 'metadata' as needed
                    payload = msg.get("payload", {})
                    headers = payload.get("headers", [])

                    # Extract relevant information (Subject, From, Snippet, Body)
                    subject = next(
                        (h["value"] for h in headers if h["name"].lower() == "subject"),
                        "No Subject",
                    )
                    sender = next(
                        (h["value"] for h in headers if h["name"].lower() == "from"),
                        "Unknown Sender",
                    )
                    snippet = msg.get("snippet", "No Snippet")
                    body = self._get_email_body(payload)  # Decode body

                    self.logger.info(
                        f"Processing email: ID={msg_id}, From='{sender}', Subject='{subject}'"
                    )
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
                            self.logger.info(
                                f"AI processing finished for email ID {email_id} ('{email_subject}')."
                            )
                            self.logger.debug(
                                f"AI Response for {email_id}: {ai_response}"
                            )
                            # Potentially take action based on AI response (e.g., reply, label)
                            # This part is application-specific and not implemented here.

                        return email_response_callback

                    # Execute the AI agent asynchronously
                    self._execute_ai_agent_async(
                        initial_query=initial_query,
                        callback=create_callback(msg_id, subject),
                    )

                    # Mark the email as read (if configured)
                    if self.mark_as_read:
                        self.logger.debug(f"Marking email {msg_id} as read.")
                        self.service.users().messages().modify(
                            userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
                        ).execute()

                except HttpError as error:
                    self.logger.error(
                        f"An HTTP error occurred processing message ID {msg_id}: {error}",
                        exc_info=True,
                    )
                except Exception as e:
                    self.logger.error(
                        f"An unexpected error occurred processing message ID {msg_id}: {e}",
                        exc_info=True,
                    )

        except HttpError as error:
            self.logger.error(
                f"An HTTP error occurred while listing emails: {error}", exc_info=True
            )
            # Handle specific errors like auth failures
            if error.resp.status == 401:
                self.logger.error(
                    "Authentication error. Credentials might be invalid or revoked."
                )
                # Consider attempting to refresh credentials or stopping the trigger
                self.credentials = (
                    None  # Force re-auth attempt on next cycle if possible
                )
        except Exception as e:
            self.logger.error(
                f"An unexpected error occurred while checking emails: {e}",
                exc_info=True,
            )

    def _get_email_body(self, payload: Dict[str, Any]) -> str:
        """Extracts and decodes the email body from the payload."""
        body = ""
        if "parts" in payload:
            # Handle multipart emails (common case)
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                if mime_type == "text/plain":
                    data = part.get("body", {}).get("data")
                    if data:
                        body += base64.urlsafe_b64decode(data).decode(
                            "utf-8", errors="replace"
                        )
                        break  # Often, the first text/plain part is sufficient
                elif mime_type == "text/html":
                    # Optionally handle HTML body if plain text is not found
                    # For simplicity, we prioritize plain text here
                    pass
                elif "parts" in part:  # Recursively check nested parts
                    nested_body = self._get_email_body(part)
                    if nested_body:  # Prefer plain text from nested parts if found
                        if part.get("mimeType", "") == "text/plain":
                            body = nested_body
                            break
                        elif not body:  # Use nested body if no plain text found yet
                            body = nested_body

        elif "body" in payload:
            # Handle single part emails
            data = payload.get("body", {}).get("data")
            mime_type = payload.get("mimeType", "")
            if data and mime_type == "text/plain":
                body = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            # Add handling for single part HTML if needed

        return body.strip() if body else "No text body found."

    async def start(self):
        """Starts the email checking loop."""
        await super().start()  # Log start message
        if not self.service:
            self.logger.error("Cannot start polling: Gmail service not initialized.")
            # Optionally raise an error or simply return to prevent running
            raise RuntimeError(
                "Gmail service failed to initialize. Cannot start trigger."
            )

        self._stop_event.clear()
        self.logger.info(
            f"Starting email polling every {self.polling_interval} seconds..."
        )
        while not self._stop_event.is_set():
            try:
                await self._check_emails()
                # Wait for the polling interval or until stop is requested
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.polling_interval
                )
            except asyncio.TimeoutError:
                # This is expected, just means the interval passed
                continue
            except Exception as e:
                self.logger.error(
                    f"Unexpected error in polling loop: {e}", exc_info=True
                )
                # Avoid rapid failure loops, wait before retrying
                await asyncio.sleep(self.polling_interval)

    async def stop(self):
        """Stops the email checking loop."""
        await super().stop()  # Log stop message
        self.logger.info("Stopping email polling...")
        self._stop_event.set()
        # No external connections to explicitly close here, service object handles its state.
        self.logger.info("GmailEmailReceivedBot stopped.")
