#!/usr/bin/env python3
"""Print the YouTube refresh token and client id for the GitHub environment secrets (SETUP-AUTOMATION.md).

Run once on your own computer, never in CI, with the channel owner's Google account:
  pip install google-auth-oauthlib
  python3 tools/publish/get_refresh_token.py path/to/client_secret.json
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
