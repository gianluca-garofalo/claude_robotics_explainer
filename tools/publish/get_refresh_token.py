#!/usr/bin/env python3
"""One-time helper, run by you on your own computer (never in CI, never by Claude): get the YouTube refresh token.

  pip install google-auth-oauthlib
  python3 tools/publish/get_refresh_token.py path/to/client_secret.json

A browser opens; sign in with the Google account that owns the Remaining Action channel (choose the channel if asked)
and grant access. The script prints the refresh token and the client id; store them, with the client secret, as the
GitHub environment secrets YOUTUBE_REFRESH_TOKEN, YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET (SETUP-AUTOMATION.md).
Keep client_secret.json outside the repository and delete it when done. Scopes requested: upload videos, and manage
them (status, thumbnail, captions): youtube.upload and youtube.force-ssl.
Refresh tokens of an OAuth app left in "Testing" expire after 7 days: set the consent screen to "In production".
"""
import json
import sys

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("pip install google-auth-oauthlib first", file=sys.stderr)
        return 1
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], scopes=SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    if not creds.refresh_token:
        print("no refresh token returned: revoke the app's access in your Google account and run again", file=sys.stderr)
        return 1
    print(json.dumps({"YOUTUBE_CLIENT_ID": creds.client_id, "YOUTUBE_REFRESH_TOKEN": creds.refresh_token}, indent=2))
    print("Store these (and the client secret) as GitHub environment secrets; do not commit them.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
