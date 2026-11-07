#!/usr/bin/env python3
"""YouTube Data API client of the workflow's staging and publishing jobs (never run by an agent).

Usage (credentials from the environment: YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN):
  python3 tools/publish/youtube.py whoami
  python3 tools/publish/youtube.py stage runs/<run> [--ledger site/ledger.json]   # private upload, idempotent
  python3 tools/publish/youtube.py publish --video-id ID [--mode public|schedule] [--delay-hours 24]
  python3 tools/publish/youtube.py delete --video-id ID
  python3 tools/publish/youtube.py playlist runs/<run> --video-id ID [--ledger site/ledger.json]   # series episodes
  YOUTUBE_BACKEND=fake YOUTUBE_FAKE_STATE=state.json: a local stand-in (tests, dry runs)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _common import CONFIG, load_json, resolve_run, utc_now, write_json  # noqa: E402

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.force-ssl"]
CAPTION_NAME = "English (Remaining Action)"
QUOTA = {"insert": 1600, "thumbnail": 50, "captions_insert": 400, "captions_list": 50, "update": 50, "list": 1,
         "delete": 50, "playlist_insert": 50, "playlist_item_insert": 50}


class PublishError(Exception):
    pass


# --------------------------------------------------------------------------- backends
class RealBackend:
    def __init__(self):
        missing = [k for k in ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN") if not os.environ.get(k)]
        if missing:
            raise PublishError(f"missing credentials in the environment: {', '.join(missing)} (GitHub environment secrets)")
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials(None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
                            client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
                            token_uri="https://oauth2.googleapis.com/token", scopes=SCOPES)
        self.yt = build("youtube", "v3", credentials=creds, cache_discovery=False)

    def channel(self):
        r = self.yt.channels().list(part="snippet,contentDetails", mine=True).execute()
        if not r.get("items"):
            raise PublishError("the authorised Google account has no YouTube channel")
        it = r["items"][0]
        return {"id": it["id"], "title": it["snippet"]["title"],
                "uploads": it["contentDetails"]["relatedPlaylists"]["uploads"]}

    def recent_uploads(self, uploads_playlist, n=50):
        r = self.yt.playlistItems().list(part="snippet", playlistId=uploads_playlist, maxResults=min(n, 50)).execute()
        return [{"video_id": i["snippet"]["resourceId"]["videoId"], "title": i["snippet"]["title"],
                 "description": i["snippet"].get("description", "")} for i in r.get("items", [])]

    def insert(self, body, video_path):
        from googleapiclient.errors import HttpError
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True, mimetype="video/mp4")
        req = self.yt.videos().insert(part="snippet,status", body=body, media_body=media, notifySubscribers=False)
        response, retry = None, 0
        while response is None:
            try:
                _, response = req.next_chunk()
            except HttpError as exc:
                if exc.resp.status in (500, 502, 503, 504) and retry < 8:
                    time.sleep(2 ** retry)
                    retry += 1
                    continue
                raise
        return response["id"]

    def set_thumbnail(self, video_id, path):
        from googleapiclient.http import MediaFileUpload
        self.yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(path), mimetype="image/jpeg")).execute()

    def captions(self, video_id):
        r = self.yt.captions().list(part="snippet", videoId=video_id).execute()
        return [i["snippet"].get("name", "") for i in r.get("items", [])]

    def insert_captions(self, video_id, path, language, name):
        from googleapiclient.http import MediaFileUpload
        body = {"snippet": {"videoId": video_id, "language": language, "name": name, "isDraft": False}}
        self.yt.captions().insert(part="snippet", body=body,
                                  media_body=MediaFileUpload(str(path), mimetype="application/octet-stream")).execute()

    def get(self, video_id):
        r = self.yt.videos().list(part="status,snippet", id=video_id).execute()
        return r["items"][0] if r.get("items") else None

    def update_status(self, video_id, status):
        self.yt.videos().update(part="status", body={"id": video_id, "status": status}).execute()

    def delete(self, video_id):
        self.yt.videos().delete(id=video_id).execute()

    def playlists(self):
        r = self.yt.playlists().list(part="snippet,status", mine=True, maxResults=50).execute()
        return [{"id": i["id"], "title": i["snippet"]["title"]} for i in r.get("items", [])]

    def create_playlist(self, title, description, privacy):
        r = self.yt.playlists().insert(part="snippet,status", body={
            "snippet": {"title": title, "description": description}, "status": {"privacyStatus": privacy}}).execute()
        return r["id"]

    def playlist_items(self, playlist_id):
        r = self.yt.playlistItems().list(part="snippet", playlistId=playlist_id, maxResults=50).execute()
        return [i["snippet"]["resourceId"]["videoId"] for i in r.get("items", [])]

    def add_to_playlist(self, playlist_id, video_id, position):
        self.yt.playlistItems().insert(part="snippet", body={"snippet": {
            "playlistId": playlist_id, "position": position,
            "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()


class FakeBackend:
    """Local stand-in with the same calls, a JSON state file and a quota tally (tests and dry runs)."""

    def __init__(self):
        self.path = Path(os.environ.get("YOUTUBE_FAKE_STATE", "youtube_fake_state.json"))
        self.s = json.loads(self.path.read_text()) if self.path.exists() else {
            "channel": {"id": "UC-fake", "title": os.environ.get("YOUTUBE_FAKE_CHANNEL", "Remaining Action"),
                        "uploads": "UU-fake"}, "videos": {}, "calls": [], "quota": 0,
            "locked_private": os.environ.get("YOUTUBE_FAKE_LOCKED") == "1"}

    def _log(self, call, units):
        self.s["calls"].append(call)
        self.s["quota"] += units
        self.path.write_text(json.dumps(self.s, indent=2))

    def channel(self):
        self._log("channels.list", QUOTA["list"])
        return self.s["channel"]

    def recent_uploads(self, uploads_playlist, n=50):
        self._log("playlistItems.list", QUOTA["list"])
        vids = list(self.s["videos"].items())[-n:]
        return [{"video_id": k, "title": v["snippet"]["title"], "description": v["snippet"]["description"]}
                for k, v in reversed(vids)]

    def insert(self, body, video_path):
        if not Path(video_path).exists():
            raise PublishError(f"video file missing: {video_path}")
        vid = "fake" + hashlib.sha1(f"{body['snippet']['title']}{len(self.s['videos'])}".encode()).hexdigest()[:7]
        self.s["videos"][vid] = {"snippet": body["snippet"], "status": dict(body["status"], uploadStatus="processed"),
                                 "thumbnail": None, "captions": []}
        self._log(f"videos.insert {vid}", QUOTA["insert"])
        return vid

    def set_thumbnail(self, video_id, path):
        self.s["videos"][video_id]["thumbnail"] = str(path)
        self._log(f"thumbnails.set {video_id}", QUOTA["thumbnail"])

    def captions(self, video_id):
        self._log(f"captions.list {video_id}", QUOTA["captions_list"])
        return list(self.s["videos"][video_id]["captions"])

    def insert_captions(self, video_id, path, language, name):
        self.s["videos"][video_id]["captions"].append(name)
        self._log(f"captions.insert {video_id}", QUOTA["captions_insert"])

    def get(self, video_id):
        self._log(f"videos.list {video_id}", QUOTA["list"])
        v = self.s["videos"].get(video_id)
        return {"id": video_id, **v} if v else None

    def update_status(self, video_id, status):
        if self.s.get("locked_private") and status.get("privacyStatus") == "public":
            status = dict(status, privacyStatus="private")       # what an unaudited API project experiences
        self.s["videos"][video_id]["status"] = dict(status, uploadStatus="processed")
        self._log(f"videos.update {video_id} {status.get('privacyStatus')}", QUOTA["update"])

    def delete(self, video_id):
        self.s["videos"].pop(video_id, None)
        self._log(f"videos.delete {video_id}", QUOTA["delete"])

    def playlists(self):
        self._log("playlists.list", QUOTA["list"])
        return [{"id": k, "title": v["title"]} for k, v in self.s.setdefault("playlists", {}).items()]

    def create_playlist(self, title, description, privacy):
        pid = "PLfake" + hashlib.sha1(title.encode()).hexdigest()[:8]
        self.s.setdefault("playlists", {})[pid] = {"title": title, "privacy": privacy, "items": []}
        self._log(f"playlists.insert {pid}", QUOTA["playlist_insert"])
        return pid

    def playlist_items(self, playlist_id):
        self._log(f"playlistItems.list {playlist_id}", QUOTA["list"])
        return list(self.s.setdefault("playlists", {})[playlist_id]["items"])

    def add_to_playlist(self, playlist_id, video_id, position):
        items = self.s["playlists"][playlist_id]["items"]
        items.insert(min(position, len(items)), video_id)
        self._log(f"playlistItems.insert {playlist_id} {video_id} at {position}", QUOTA["playlist_item_insert"])


def backend():
    return FakeBackend() if os.environ.get("YOUTUBE_BACKEND") == "fake" else RealBackend()


# --------------------------------------------------------------------------- commands
def check_channel(b) -> dict:
    ch = b.channel()
    expected = load_json(CONFIG / "channel.json")["youtube"].get("expected_channel_title")
    if expected and ch["title"] != expected:
        raise PublishError(f"authorised channel is {ch['title']!r}, expected {expected!r}: refusing to upload")
    return ch


def stage(run: Path, ledger_path: Path | None) -> dict:
    meta = load_json(run / "video" / "final" / "youtube.json")
    b = backend()
    ch = check_channel(b)
    video_id, reused = None, False
    if ledger_path and ledger_path.exists():
        entry = json.loads(ledger_path.read_text()).get("runs", {}).get(run.name, {})
        if entry.get("video_id") and b.get(entry["video_id"]):
            video_id, reused = entry["video_id"], True
    if video_id is None:
        for v in b.recent_uploads(ch["uploads"]):
            if meta["marker"] in v["description"]:
                video_id, reused = v["video_id"], True
                break
    if video_id is None:
        video_id = b.insert({"snippet": meta["snippet"], "status": meta["status"]}, run / meta["files"]["video"])
    result = {"video_id": video_id, "reused": reused, "channel": ch["title"], "privacy": meta["status"]["privacyStatus"],
              "url": f"https://youtu.be/{video_id}", "studio_url": f"https://studio.youtube.com/video/{video_id}/edit",
              "thumbnail_set": False, "captions_set": False, "warnings": []}
    try:
        b.set_thumbnail(video_id, run / meta["files"]["thumbnail"])
        result["thumbnail_set"] = True
    except Exception as exc:                      # custom thumbnails need a phone-verified channel
        result["warnings"].append(f"thumbnail not set: {str(exc)[:200]} (verify the channel at youtube.com/verify)")
    try:
        if CAPTION_NAME not in b.captions(video_id):
            b.insert_captions(video_id, run / meta["files"]["captions"], meta["snippet"]["defaultLanguage"],
                              CAPTION_NAME)
        result["captions_set"] = True
    except Exception as exc:
        result["warnings"].append(f"captions not uploaded: {str(exc)[:200]}")
    result["staged_at"] = utc_now()
    write_json(run / "publish" / "stage.json", result)
    return result


def publish(video_id: str, mode: str, delay_hours: float) -> dict:
    b = backend()
    check_channel(b)
    v = b.get(video_id)
    if v is None:
        raise PublishError(f"video {video_id} not found on the channel")
    st = dict(v["status"])
    if st.get("privacyStatus") == "public":
        return {"video_id": video_id, "privacy": "public", "changed": False}
    keep = {k: st[k] for k in ("embeddable", "license", "publicStatsViewable", "selfDeclaredMadeForKids",
                               "containsSyntheticMedia") if k in st}
    if mode == "schedule":
        at = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=delay_hours)).replace(microsecond=0)
        new = dict(keep, privacyStatus="private", publishAt=at.isoformat().replace("+00:00", "Z"))
    else:
        new = dict(keep, privacyStatus="public")
    b.update_status(video_id, new)
    after = b.get(video_id)["status"]
    if mode == "public" and after.get("privacyStatus") != "public":
        raise PublishError("YouTube kept the video private. Uploads from an API project that has not passed the "
                           "YouTube API audit stay private (locked); see SETUP-AUTOMATION.md, step 'API audit'. "
                           "Until it passes, set the repository variable YOUTUBE_UPLOAD=manual: the pipeline then "
                           "prepares the files and you upload the approved video by hand.")
    return {"video_id": video_id, "privacy": after.get("privacyStatus"), "publish_at": after.get("publishAt"),
            "changed": True}


def playlist(run: Path, video_id: str, ledger_path: Path | None) -> dict:
    """Add a series episode to its playlist, in episode order; idempotent."""
    ep_p = run / "episode.json"
    if not ep_p.exists():
        return {"skipped": "not a series episode"}
    ep = json.loads(ep_p.read_text(encoding="utf-8"))
    led = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path and ledger_path.exists() else {}
    known = led.get("series", {}).get(ep["series"], {})
    b = backend()
    check_channel(b)
    pls = b.playlists()
    pid = known.get("playlist_id") if known.get("playlist_id") in {p["id"] for p in pls} else None
    pid = pid or next((p["id"] for p in pls if p["title"] == ep["playlist"]["title"]), None)
    created = pid is None
    if created:
        pid = b.create_playlist(ep["playlist"]["title"], ep["playlist"].get("description", ""),
                                ep["playlist"].get("privacy", "public"))
    items = b.playlist_items(pid)
    if video_id in items:
        return {"playlist_id": pid, "added": False, "created": created, "reason": "already in the playlist"}
    order = {e.get("video_id"): int(e["episode"]) for e in led.get("runs", {}).values()
             if e.get("series") == ep["series"] and e.get("video_id") and e.get("episode") is not None}
    position = sum(1 for v in items if order.get(v, 10 ** 6) < int(ep["episode"]))
    b.add_to_playlist(pid, video_id, position)
    return {"playlist_id": pid, "playlist_url": f"https://www.youtube.com/playlist?list={pid}", "added": True,
            "created": created, "position": position}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("whoami")
    s = sub.add_parser("stage")
    s.add_argument("run")
    s.add_argument("--ledger")
    p = sub.add_parser("publish")
    p.add_argument("--video-id", required=True)
    p.add_argument("--mode", choices=["public", "schedule"])
    p.add_argument("--delay-hours", type=float)
    d = sub.add_parser("delete")
    d.add_argument("--video-id", required=True)
    pl = sub.add_parser("playlist")
    pl.add_argument("run")
    pl.add_argument("--video-id", required=True)
    pl.add_argument("--ledger")
    a = ap.parse_args()
    try:
        if a.cmd == "whoami":
            out = check_channel(backend())
        elif a.cmd == "stage":
            out = stage(resolve_run(a.run), Path(a.ledger) if a.ledger else None)
        elif a.cmd == "publish":
            yt = load_json(CONFIG / "channel.json")["youtube"]
            out = publish(a.video_id, a.mode or yt.get("publish_mode", "public"),
                          a.delay_hours if a.delay_hours is not None else yt.get("schedule_delay_hours", 0))
        elif a.cmd == "playlist":
            out = playlist(resolve_run(a.run), a.video_id, Path(a.ledger) if a.ledger else None)
        else:
            backend().delete(a.video_id)
            out = {"video_id": a.video_id, "deleted": True}
    except PublishError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
