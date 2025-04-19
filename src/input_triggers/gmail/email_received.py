# src/input_triggers/gmail/email_received.py
import asyncio
import os
import sys
import base64
import email
from datetime import datetime, timezone, timedelta
from typing import Optional, Set, Dict, Any, List
from pathlib import Path

# Use Pathlib and ensure src is discoverable
SRC_DIR = Path(__file__).resolve().parent.parent.parent # gmail -> input_triggers -> src
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Import base class
from input_triggers.input_triggers import InputTrigger

# Google API Imports (handle optional import)
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False
    print("WARNING: Google API libraries not found. Install them with: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    # Define dummy types for type hinting if libs are missing
    Credentials = Any # type: ignore
    HttpError = Exception # type: ignore

# Default config path relative to this file
DEFAULT_CONFIG_PATH = Path(__file__).parent / "email_received.json"
DEFAULT_PROCESSED_IDS_FILE = Path(__file__).parent / "processed_email_ids.json"

class EmailReceivedTrigger(InputTrigger):
    """
    Gmail input trigger using Google API.
    Polls for new emails matching a query and triggers the AI agent.
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Gmail email listener.

        Args:
            config_path: Path to the configuration JSON file.
                         Defaults to email_received.json in the same directory.
        """
        if not GOOGLE_LIBS_AVAILABLE:
            raise ImportError("Required Google API libraries are not installed.")

        # Initialize base class (loads config, sets up logger)
        super().__init__(config_path=config_path or str(DEFAULT_CONFIG_PATH))

        self.service: Optional[Any] = None # Gmail API service object
        self.polling_interval_seconds: int = 300 # Default 5 minutes
        self.gmail_query: str = "is:unread" # Default query
        self.user_id: str = "me"
        self.scopes: List[str] = ['https://www.googleapis.com/auth/gmail.modify'] # Modify needed to mark as read
        self.credentials_path: Optional[Path] = None
        self.token_path: Optional[Path] = None
        self.processed_ids_path: Path = DEFAULT_PROCESSED_IDS_FILE
        self.processed_ids: Set[str] = set()
        self.task: Optional[asyncio.Task] = None
        self.mark_as_read: bool = True # Configurable option

    @property
    def name(self) -> str:
        """Get the name of the event listener."""
        return self.config.get("trigger_name", "GmailTrigger")

    async def initialize(self):
        """Initialize the Gmail API service and load state."""
        await super().initialize() # Sets up self.loop

        # Load configuration specifics
        self.polling_interval_seconds = self.config.get("polling_interval_minutes", 5) * 60
        self.gmail_query = self.config.get("gmail_query", "is:unread")
        self.user_id = self.config.get("user_id", "me")
        self.scopes = self.config.get("scopes", ['https://www.googleapis.com/auth/gmail.modify'])
        self.mark_as_read = self.config.get("mark_as_read", True)

        creds_path_str = self.config.get("gmail_credentials_path")
        token_path_str = self.config.get("gmail_token_path")
        processed_ids_path_str = self.config.get("processed_ids_path", str(DEFAULT_PROCESSED_IDS_FILE))

        if not creds_path_str:
            self.logger.critical("Missing 'gmail_credentials_path' in configuration.")
            raise ValueError("Gmail credentials path missing in configuration.")
        self.credentials_path = Path(creds_path_str)
        self.token_path = Path(token_path_str) if token_path_str else None # Token path is optional initially
        self.processed_ids_path = Path(processed_ids_path_str)

        if not self.credentials_path.exists():
             self.logger.critical(f"Gmail credentials file not found: {self.credentials_path}")
             raise FileNotFoundError(f"Gmail credentials file not found: {self.credentials_path}")

        # Load processed IDs
        self._load_processed_ids()

        # Authenticate and build service
        creds = await self._get_credentials()
        if not creds:
             self.logger.critical("Failed to obtain Gmail credentials.")
             raise RuntimeError("Gmail authentication failed.")

        try:
            self.service = build('gmail', 'v1', credentials=creds, cache_discovery=False) # Avoid discovery cache issues
            self.logger.info("Gmail API service built successfully.")
        except Exception as e:
            self.logger.critical(f"Failed to build Gmail service: {e}", exc_info=True)
            raise

        self.logger.info(f"Gmail trigger '{self.name}' initialized. Polling interval: {self.polling_interval_seconds}s. Query: '{self.gmail_query}'")


    async def _get_credentials(self) -> Optional[Credentials]:
        """Gets valid Google API credentials, handling token refresh and initial flow."""
        creds = None
        if self.token_path and self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
                self.logger.info(f"Loaded credentials from {self.token_path}")
            except Exception as e:
                 self.logger.warning(f"Failed to load token file {self.token_path}: {e}. Will attempt refresh/re-auth.")
                 creds = None # Ensure creds is None if loading failed

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self.logger.info("Credentials expired, attempting refresh...")
                try:
                    # Run refresh in executor to avoid blocking asyncio loop
                    await self.loop.run_in_executor(None, creds.refresh, Request())
                    self.logger.info("Credentials refreshed successfully.")
                except Exception as e:
                    self.logger.error(f"Failed to refresh credentials: {e}. Need re-authentication.", exc_info=True)
                    creds = None # Force re-authentication
                else:
                    # Save the refreshed credentials
                    self._save_token(creds)
            else:
                self.logger.info("No valid token found, initiating OAuth flow...")
                if not self.credentials_path or not self.credentials_path.exists():
                     self.logger.error("Cannot initiate OAuth flow: credentials.json path invalid or file missing.")
                     return None
                try:
                    # Run the flow in an executor thread as it might involve user interaction / blocking calls
                    flow = await self.loop.run_in_executor(
                        None,
                        InstalledAppFlow.from_client_secrets_file,
                        str(self.credentials_path), self.scopes
                    )
                    # Note: run_local_server might block. Consider alternatives for headless environments.
                    # For server environments, you'd typically use a service account or a web-based OAuth flow.
                    # This example assumes an environment where a local browser can be opened.
                    creds = await self.loop.run_in_executor(None, flow.run_local_server, port=0)
                    self.logger.info("OAuth flow completed successfully.")
                    # Save the credentials for the next run
                    self._save_token(creds)
                except Exception as e:
                    self.logger.critical(f"OAuth flow failed: {e}", exc_info=True)
                    return None
        return creds

    def _save_token(self, creds: Credentials):
        """Saves the credentials token to the configured path."""
        if self.token_path:
            try:
                with open(self.token_path, 'w') as token_file:
                    token_file.write(creds.to_json())
                self.logger.info(f"Credentials saved to {self.token_path}")
            except Exception as e:
                self.logger.error(f"Failed to save token to {self.token_path}: {e}", exc_info=True)
        else:
            self.logger.warning("No 'gmail_token_path' configured. Credentials not saved.")


    async def start(self):
        """Start the email polling loop."""
        await super().start()

        if not self.service:
            self.logger.error("Gmail service not initialized. Cannot start polling.")
            raise RuntimeError("Cannot start Gmail trigger: service not initialized.")

        if self.task and not self.task.done():
            self.logger.warning("Start called but polling task is already running.")
            return self.task

        self.logger.info("Starting email polling task...")
        self.task = asyncio.create_task(self._poll_emails_loop(), name=f"{self.name}_poll")
        self.logger.info(f"Email polling task '{self.task.get_name()}' created.")
        return self.task

    async def stop(self):
        """Stop the email polling loop and save state."""
        await super().stop()

        if self.task:
            task_name = self.task.get_name()
            if not self.task.done():
                self.logger.info(f"Cancelling polling task '{task_name}'...")
                self.task.cancel()
                try:
                    await self.task
                except asyncio.CancelledError:
                    self.logger.info(f"Polling task '{task_name}' cancelled successfully.")
                except Exception as e:
                    self.logger.error(f"Error during polling task '{task_name}' cancellation/cleanup: {e}", exc_info=True)
            else:
                 exception = self.task.exception()
                 if exception:
                      self.logger.error(f"Polling task '{task_name}' finished with an exception: {exception}", exc_info=exception)
                 else:
                      self.logger.info(f"Polling task '{task_name}' already finished.")
        self.task = None
        self._save_processed_ids() # Save state on stop
        self.logger.info(f"Gmail trigger '{self.name}' stopped.")

    def _load_processed_ids(self):
        """Load processed email IDs from the state file."""
        if self.processed_ids_path.exists():
            try:
                with open(self.processed_ids_path, 'r') as f:
                    ids_list = json.load(f)
                    self.processed_ids = set(ids_list)
                self.logger.info(f"Loaded {len(self.processed_ids)} processed email IDs from {self.processed_ids_path}")
            except Exception as e:
                self.logger.error(f"Failed to load processed IDs from {self.processed_ids_path}: {e}. Starting fresh.", exc_info=True)
                self.processed_ids = set()
        else:
            self.logger.info(f"Processed IDs file not found ({self.processed_ids_path}). Starting fresh.")
            self.processed_ids = set()

    def _save_processed_ids(self):
        """Save processed email IDs to the state file."""
        try:
            with open(self.processed_ids_path, 'w') as f:
                json.dump(list(self.processed_ids), f) # Convert set to list for JSON
            self.logger.info(f"Saved {len(self.processed_ids)} processed email IDs to {self.processed_ids_path}")
        except Exception as e:
            self.logger.error(f"Failed to save processed IDs to {self.processed_ids_path}: {e}", exc_info=True)


    async def _poll_emails_loop(self):
        """The main loop that periodically checks for new emails."""
        self.logger.info("Email polling loop started.")
        while True:
            try:
                self.logger.debug(f"Checking for new emails (Query: '{self.gmail_query}')...")
                # Run blocking API call in executor
                messages = await self.loop.run_in_executor(None, self._fetch_new_message_ids)

                if messages:
                    self.logger.info(f"Found {len(messages)} potentially new email(s).")
                    for message_summary in messages:
                        message_id = message_summary['id']
                        if message_id not in self.processed_ids:
                            self.logger.info(f"Processing new email ID: {message_id}")
                            # Process each new email concurrently
                            asyncio.create_task(self._process_email(message_id))
                        else:
                            self.logger.debug(f"Skipping already processed email ID: {message_id}")

                else:
                    self.logger.debug("No new messages found matching query.")

                # Wait for the next polling interval
                self.logger.debug(f"Sleeping for {self.polling_interval_seconds} seconds...")
                await asyncio.sleep(self.polling_interval_seconds)

            except asyncio.CancelledError:
                self.logger.info("Polling loop cancelled.")
                break # Exit the loop if cancelled
            except HttpError as error:
                 self.logger.error(f"An API error occurred during polling: {error}", exc_info=True)
                 # Implement backoff strategy here if needed
                 await asyncio.sleep(self.polling_interval_seconds * 2) # Simple backoff
            except Exception as e:
                self.logger.error(f"An unexpected error occurred in the polling loop: {e}", exc_info=True)
                # Avoid rapid failure loops
                await asyncio.sleep(self.polling_interval_seconds)


    def _fetch_new_message_ids(self) -> List[Dict[str, str]]:
        """Calls the Gmail API to list messages matching the query. (Blocking)"""
        try:
            results = self.service.users().messages().list(
                userId=self.user_id, q=self.gmail_query
            ).execute()
            messages = results.get('messages', [])
            return messages
        except HttpError as error:
            # Handle specific errors like 401/403 for auth issues if needed
            self.logger.error(f"API error fetching message list: {error}")
            # Potentially trigger re-authentication here if it's an auth error
            raise # Re-raise to be caught by the loop handler
        except Exception as e:
            self.logger.error(f"Unexpected error fetching message list: {e}")
            raise # Re-raise


    async def _process_email(self, message_id: str):
        """Fetches, parses, and triggers processing for a single email."""
        try:
            # Fetch full email (run blocking API call in executor)
            message_data = await self.loop.run_in_executor(
                None,
                lambda: self.service.users().messages().get(userId=self.user_id, id=message_id, format='raw').execute()
            )

            if not message_data or 'raw' not in message_data:
                 self.logger.warning(f"Could not retrieve raw content for message ID: {message_id}")
                 self.processed_ids.add(message_id) # Mark as processed to avoid retrying
                 return

            # Parse email content
            email_content = self._parse_email_content(message_data)

            if not email_content['body']:
                 self.logger.warning(f"Could not extract text body from email ID: {message_id}")
                 self.processed_ids.add(message_id) # Mark as processed
                 # Optionally mark as read even if body is empty
                 if self.mark_as_read:
                     await self._mark_email_as_read(message_id)
                 return

            self.logger.info(f"Extracted content from email {message_id}. Subject: {email_content['subject'][:50]}...")
            self.logger.debug(f"Email Body Snippet: {email_content['body'][:100]}...")

            # --- Define the callback for the AI agent ---
            def final_callback(agent_response: str):
                # What to do with the AI response for an email?
                # Options: Log it, send a reply email, update a database, etc.
                # For now, just log it.
                self.logger.info(f"Received final AI response for email {message_id}. Length: {len(agent_response)}")
                self.logger.debug(f"AI Response for email {message_id}: {agent_response[:200]}...")
                # Add logic here to handle the response (e.g., send reply)

            # --- Trigger AI Agent ---
            # Decide what part of the email to send as the query
            # Example: Combine subject and body
            query = f"Subject: {email_content['subject']}\n\nBody:\n{email_content['body']}"
            self._execute_ai_agent_async(query, final_callback)

            # Mark email as processed *after* initiating AI processing
            self.processed_ids.add(message_id)

            # Mark email as read in Gmail if configured
            if self.mark_as_read:
                await self._mark_email_as_read(message_id)

        except HttpError as error:
            self.logger.error(f"API error processing email ID {message_id}: {error}", exc_info=True)
            # Don't mark as processed on API errors, allow retry? Or add to a failed queue?
            # For simplicity now, we might still mark it processed if retries are complex.
            self.processed_ids.add(message_id)
        except Exception as e:
            self.logger.error(f"Error processing email ID {message_id}: {e}", exc_info=True)
            self.processed_ids.add(message_id) # Mark as processed on unexpected errors


    def _parse_email_content(self, message_data: Dict[str, Any]) -> Dict[str, str]:
        """Parses raw email data to extract subject, sender, and text body."""
        content = {'subject': '', 'from': '', 'body': ''}
        try:
            msg_raw = base64.urlsafe_b64decode(message_data['raw'].encode('ASCII'))
            msg = email.message_from_bytes(msg_raw)

            content['subject'] = msg.get('Subject', '')
            content['from'] = msg.get('From', '')

            # Find the plain text body part
            if msg.is_multipart():
                for part in msg.walk():
                    ctype = part.get_content_type()
                    cdispo = str(part.get('Content-Disposition'))
                    # Look for plain text parts that are not attachments
                    if ctype == 'text/plain' and 'attachment' not in cdispo:
                        try:
                            charset = part.get_content_charset() or 'utf-8' # Default to utf-8
                            content['body'] = part.get_payload(decode=True).decode(charset, errors='replace')
                            break # Found plain text body
                        except Exception as decode_err:
                             self.logger.warning(f"Could not decode text/plain part with charset {charset}: {decode_err}")
                             # Try default decoding as fallback
                             try:
                                 content['body'] = part.get_payload(decode=True).decode('utf-8', errors='replace')
                                 break
                             except: pass # Ignore fallback error
            else:
                # Not multipart, assume payload is the body if it's text/plain
                 ctype = msg.get_content_type()
                 if ctype == 'text/plain':
                    try:
                        charset = msg.get_content_charset() or 'utf-8'
                        content['body'] = msg.get_payload(decode=True).decode(charset, errors='replace')
                    except Exception as decode_err:
                         self.logger.warning(f"Could not decode non-multipart body with charset {charset}: {decode_err}")
                         try:
                             content['body'] = msg.get_payload(decode=True).decode('utf-8', errors='replace')
                         except: pass # Ignore fallback error

            # Simple cleanup
            content['body'] = content['body'].strip()

        except Exception as e:
            self.logger.error(f"Failed to parse email content for ID {message_data.get('id', 'N/A')}: {e}", exc_info=True)

        return content


    async def _mark_email_as_read(self, message_id: str):
        """Marks the specified email as read by removing the UNREAD label."""
        self.logger.debug(f"Marking email {message_id} as read...")
        try:
            # Run blocking API call in executor
            await self.loop.run_in_executor(
                None,
                lambda: self.service.users().messages().modify(
                    userId=self.user_id,
                    id=message_id,
                    body={'removeLabelIds': ['UNREAD']}
                ).execute()
            )
            self.logger.info(f"Successfully marked email {message_id} as read.")
        except HttpError as error:
            self.logger.error(f"Failed to mark email {message_id} as read: {error}", exc_info=True)
        except Exception as e:
             self.logger.error(f"Unexpected error marking email {message_id} as read: {e}", exc_info=True)

