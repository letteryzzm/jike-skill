#!/usr/bin/env python3
"""
Jike API Client (standalone)
Run directly: python3 scripts/client.py feed --access-token T --refresh-token T
No pip install required — only needs `requests`.

Author: Claude Opus 4.5
"""

import argparse
import json
import sys
from typing import Optional

import requests

API_BASE = "https://api.ruguoapp.com"
HEADERS = {
    "Origin": "https://web.okjike.com",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 "
        "Mobile/15E148 Safari/604.1"
    ),
    "Accept": "application/json, text/plain, */*",
    "DNT": "1",
}


def _call(method: str, path: str, access_token: str, refresh_token: str, retry: bool = True, **kwargs):
    hdrs = {**HEADERS, "Content-Type": "application/json", "x-jike-access-token": access_token}
    resp = requests.request(method, f"{API_BASE}{path}", headers=hdrs, **kwargs)

    if resp.status_code == 401 and retry:
        new_access, new_refresh = _refresh(refresh_token)
        return _call(method, path, new_access, new_refresh, retry=False, **kwargs)

    resp.raise_for_status()
    return resp.json() if resp.content else {}


def _refresh(refresh_token: str) -> tuple:
    resp = requests.post(
        f"{API_BASE}/app_auth_tokens.refresh",
        headers={**HEADERS, "Content-Type": "application/json", "x-jike-refresh-token": refresh_token},
        json={},
    )
    resp.raise_for_status()
    return (
        resp.headers.get("x-jike-access-token", ""),
        resp.headers.get("x-jike-refresh-token", refresh_token),
    )


# ── API Functions ─────────────────────────────────────────

def feed(at: str, rt: str, limit: int = 20, load_more_key: Optional[str] = None) -> dict:
    body: dict = {"limit": limit}
    if load_more_key:
        body["loadMoreKey"] = load_more_key
    return _call("POST", "/1.0/personalUpdate/followingUpdates", at, rt, json=body)


def create_post(at: str, rt: str, content: str, picture_keys: Optional[list] = None) -> dict:
    return _call("POST", "/1.0/originalPosts/create", at, rt, json={"content": content, "pictureKeys": picture_keys or []})


def delete_post(at: str, rt: str, post_id: str) -> dict:
    return _call("POST", "/1.0/originalPosts/remove", at, rt, json={"id": post_id})


def add_comment(at: str, rt: str, post_id: str, content: str) -> dict:
    return _call("POST", "/1.0/comments/add", at, rt, json={
        "targetType": "ORIGINAL_POST", "targetId": post_id,
        "content": content, "syncToPersonalUpdates": False, "pictureKeys": [], "force": False,
    })


def delete_comment(at: str, rt: str, comment_id: str) -> dict:
    return _call("POST", "/1.0/comments/remove", at, rt, json={"id": comment_id, "targetType": "ORIGINAL_POST"})


def search(at: str, rt: str, keyword: str, limit: int = 20) -> dict:
    return _call("POST", "/1.0/search/integrate", at, rt, json={"keyword": keyword, "limit": limit})


def profile(at: str, rt: str, username: str) -> dict:
    return _call("GET", f"/1.0/users/profile?username={username}", at, rt)


def user_posts(at: str, rt: str, username: str, limit: int = 20, load_more_key: Optional[str] = None) -> dict:
    body: dict = {"username": username, "limit": limit}
    if load_more_key:
        body["loadMoreKey"] = load_more_key
    return _call("POST", "/1.0/userPost/listMore", at, rt, json=body)


def notifications(at: str, rt: str) -> dict:
    return {
        "unread": _call("GET", "/1.0/notifications/unread", at, rt),
        "list": _call("POST", "/1.0/notifications/list", at, rt, json={}),
    }


# ── CLI ───────────────────────────────────────────────────

def main():
    p = argparse.ArgumentParser(description="Jike API client")
    p.add_argument("--access-token", required=True)
    p.add_argument("--refresh-token", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("feed").add_argument("--limit", type=int, default=20)
    sp = sub.add_parser("post"); sp.add_argument("--content", required=True)
    sub.add_parser("delete-post").add_argument("--post-id", required=True)
    sp = sub.add_parser("comment"); sp.add_argument("--post-id", required=True); sp.add_argument("--content", required=True)
    sub.add_parser("delete-comment").add_argument("--comment-id", required=True)
    sp = sub.add_parser("search"); sp.add_argument("--keyword", required=True); sp.add_argument("--limit", type=int, default=20)
    sub.add_parser("profile").add_argument("--username", required=True)
    sp = sub.add_parser("user-posts"); sp.add_argument("--username", required=True); sp.add_argument("--limit", type=int, default=20)
    sub.add_parser("notifications")

    args = p.parse_args()
    at, rt = args.access_token, args.refresh_token

    dispatch = {
        "feed": lambda: feed(at, rt, args.limit),
        "post": lambda: create_post(at, rt, args.content),
        "delete-post": lambda: delete_post(at, rt, args.post_id),
        "comment": lambda: add_comment(at, rt, args.post_id, args.content),
        "delete-comment": lambda: delete_comment(at, rt, args.comment_id),
        "search": lambda: search(at, rt, args.keyword, args.limit),
        "profile": lambda: profile(at, rt, args.username),
        "user-posts": lambda: user_posts(at, rt, args.username, args.limit),
        "notifications": lambda: notifications(at, rt),
    }

    try:
        result = dispatch[args.cmd]()
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()
    except requests.HTTPError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
