from caldav import DAVClient
from caldav.lib.error import AuthorizationError
from requests.auth import HTTPBasicAuth

def discover_icloud_calendars(username: str, app_password: str) -> None:
    """
    Authenticate with iCloud CalDAV, and list calendar URLs available to the user.

    :param username: iCloud email address (usually Apple ID email)
    :param app_password: App-specific password generated at appleid.apple.com
    """
    url = "https://caldav.icloud.com/"
    try:
        client = DAVClient(url, auth=HTTPBasicAuth(username, app_password))
        principal = client.principal()
        calendars = principal.calendars()

        if not calendars:
            print("✅ Login succeeded, but no calendars found.")
        for cal in calendars:
            print(f"📅 Calendar name: {cal.name}")
            print(f"🔗 Calendar URL: {cal.url}\n")

    except AuthorizationError:
        print("❌ Authorization failed. Check your email and app-specific password.")
    except Exception as e:
        print(f"❌ Error: {str(e)}")

# Replace with your credentials
discover_icloud_calendars("someone@icloud.com", "abc-123")
