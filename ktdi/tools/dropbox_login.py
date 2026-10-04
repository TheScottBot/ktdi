"""Get the DROPBOX_REFRESH_TOKEN for /rpg, once:  python -m ktdi.tools.dropbox_login

You approve the bot's Dropbox app in your browser; Dropbox gives you a code; this swaps the code for a refresh token
for your .env. Nothing is saved or sent anywhere else. See README: RPG rulebooks.
"""

import getpass
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
TOKEN_URL = "https://api.dropbox.com/oauth2/token"


def main() -> None:
    print("Dropbox login for KTDI's /rpg. You'll need the App key and App secret from your Dropbox app's settings.\n")
    app_key = input("App key: ").strip()
    app_secret = getpass.getpass("App secret (not shown as you type): ").strip()
    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode(
        {"client_id": app_key, "response_type": "code", "token_access_type": "offline"})
    print(f"\n1. Open this, sign in to Dropbox and allow the app:\n\n   {url}\n")
    code = input("2. Paste the code Dropbox shows you: ").strip()
    data = urllib.parse.urlencode({"code": code, "grant_type": "authorization_code", "client_id": app_key,
                                   "client_secret": app_secret}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(TOKEN_URL, data=data), timeout=30) as response:
            body = json.load(response)
    except urllib.error.HTTPError as error:
        sys.exit(f"\nDropbox said no ({error.code}): {error.read().decode(errors='replace')[:300]}\n"
                 "Check the key and secret, and use a fresh code (each one works once, for a few minutes).")
    if "refresh_token" not in body:
        sys.exit("\nDropbox didn't send a refresh token. Try again with a fresh code.")
    print("\n3. Done. Put these in the bot's .env (keep them secret, like the Discord token):\n")
    print(f"DROPBOX_APP_KEY={app_key}")
    print("DROPBOX_APP_SECRET=<the App secret you typed>")
    print(f"DROPBOX_REFRESH_TOKEN={body['refresh_token']}")


if __name__ == "__main__":
    main()
