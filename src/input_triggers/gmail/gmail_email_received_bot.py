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
            self.logger.info("Gmail API service initialized successfully.")
        except Exception as e:
            self.logger.error(f"Error initializing Gmail service: {e}", exc_info=True)
            # Prevent starting if initialization fails critically
            raise RuntimeError(f"Failed to initialize Gmail service: {e}")

    def _authenticate_gmail_api(self):
        """
        Authenticates the user with Gmail API using OAuth2 and returns the Gmail service object.

        :return: Authorized Gmail service resource.
        :rtype: googleapiclient.discovery.Resource
        """
        creds: Optional[Credentials] = None

        access_token_file = self.trigger_config.get("access_token_file", DEFAULT_TOKEN_PATH)

        if os.path.exists(access_token_file):
            creds = Credentials.from_authorized_user_file(access_token_file, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                client_secrets_file = self.trigger_config.get("client_secrets_file", DEFAULT_CREDENTIALS_PATH)

                if os.path.exists(client_secrets_file):
                    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
                    creds = flow.run_local_server(port=0) 
                else:
                    self.logger.error(f"Client secrets file not found: {client_secrets_file}")
                    return None

            with open(access_token_file, 'w') as token:
                token.write(creds.to_json())

        service = build('gmail', 'v1', credentials=creds)
        return service

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
