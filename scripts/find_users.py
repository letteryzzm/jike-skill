#!/usr/bin/env python3
"""
Find Jike users matching technical founder criteria.

Searches by keywords, deduplicates users, fetches full profiles,
extracts contact info and age from bio.

Usage:
  python3 scripts/find_users.py \
    --keywords "独立开发,开源,hackathon,冷启动" \
    --access-token TOKEN --refresh-token TOKEN \
    [--pages 2] [--output users.json]

Author: Claude Sonnet 4.6
"""

import argparse
import json
import re
import sys
import time
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
RATE_LIMIT_DELAY = 0.5


def _call(method, path, at, rt, retry=True, **kwargs):
    hdrs = {**HEADERS, "Content-Type": "application/json", "x-jike-access-token": at}
    resp = requests.request(method, f"{API_BASE}{path}", headers=hdrs, **kwargs)
    if resp.status_code == 401 and retry:
        at, rt = _refresh(rt)
        return _call(method, path, at, rt, retry=False, **kwargs)
    resp.raise_for_status()
    return resp.json() if resp.content else {}, at, rt


def _refresh(rt):
    resp = requests.post(
        f"{API_BASE}/app_auth_tokens.refresh",
        headers={**HEADERS, "Content-Type": "application/json", "x-jike-refresh-token": rt},
        json={},
    )
    resp.raise_for_status()
    return (
        resp.headers.get("x-jike-access-token", ""),
        resp.headers.get("x-jike-refresh-token", rt),
    )


def search_keyword(keyword, at, rt, pages=2):
    posts = []
    load_more_key = None
    for _ in range(pages):
        body = {"keyword": keyword, "limit": 20}
        if load_more_key:
            body["loadMoreKey"] = load_more_key
        try:
            data, at, rt = _call("POST", "/1.0/search/integrate", at, rt, json=body)
        except requests.HTTPError as e:
            print(f"  搜索 '{keyword}' 出错: {e}", file=sys.stderr)
            break
        page_posts = data.get("data", [])
        posts.extend(page_posts)
        load_more_key = data.get("loadMoreKey")
        if not load_more_key:
            break
        time.sleep(RATE_LIMIT_DELAY)
    return posts, at, rt


def extract_users_from_posts(posts):
    users = {}
    for post in posts:
        user = post.get("user", {})
        if not user:
            continue
        username = user.get("username") or user.get("id")
        if not username or username in users:
            continue
        users[username] = {
            "username": username,
            "screen_name": user.get("screenName", ""),
        }
    return users


def fetch_profile(username, at, rt):
    try:
        data, at, rt = _call("GET", f"/1.0/users/profile?username={username}", at, rt)
        user = data.get("user", data)
        return {
            "username": username,
            "screen_name": user.get("screenName", ""),
            "bio": user.get("bio", "") or "",
            "profile_url": f"https://okjike.com/u/{username}",
            "followers_count": user.get("followersCount", 0),
        }, at, rt
    except requests.HTTPError:
        return None, at, rt


def extract_contact(bio: str) -> str:
    contacts = []
    wechat = re.search(r'微信[：:]\s*(\S+)', bio)
    if wechat:
        contacts.append(f"微信: {wechat.group(1)}")
    twitter = re.search(r'(?:twitter|x\.com|推特)[：:\s@]*([A-Za-z0-9_]+)', bio, re.IGNORECASE)
    if twitter:
        contacts.append(f"Twitter: @{twitter.group(1)}")
    email = re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}', bio)
    if email:
        contacts.append(f"Email: {email.group(0)}")
    github = re.search(r'github\.com/([A-Za-z0-9_-]+)', bio, re.IGNORECASE)
    if github:
        contacts.append(f"GitHub: github.com/{github.group(1)}")
    return "、".join(contacts) if contacts else ""


def extract_age(bio: str) -> str:
    age = re.search(r'(\d{2})\s*(?:岁|y/?o\b)', bio)
    if age:
        a = int(age.group(1))
        if 14 <= a <= 35:
            return f"{a}岁"
    return ""


def main():
    p = argparse.ArgumentParser(description="按关键词搜索即刻技术型用户")
    p.add_argument("--keywords", required=True, help="逗号分隔的关键词，如 '独立开发,开源,hackathon'")
    p.add_argument("--access-token", required=True)
    p.add_argument("--refresh-token", required=True)
    p.add_argument("--pages", type=int, default=2, help="每个关键词抓取的页数（默认2）")
    p.add_argument("--output", "-o", default=None, help="输出 JSON 文件路径，不填则输出到 stdout")
    args = p.parse_args()

    at, rt = args.access_token, args.refresh_token
    keywords = [k.strip() for k in args.keywords.split(",") if k.strip()]

    all_users: dict = {}
    for kw in keywords:
        print(f"搜索关键词「{kw}」...", file=sys.stderr, end=" ", flush=True)
        posts, at, rt = search_keyword(kw, at, rt, pages=args.pages)
        users = extract_users_from_posts(posts)
        print(f"帖子 {len(posts)} 条，新用户 {sum(1 for u in users if u not in all_users)} 个", file=sys.stderr)
        for username, basic in users.items():
            if username not in all_users:
                all_users[username] = basic
                all_users[username]["found_via"] = [kw]
            else:
                all_users[username]["found_via"].append(kw)
        time.sleep(RATE_LIMIT_DELAY)

    total = len(all_users)
    print(f"\n共 {total} 个唯一用户，开始拉取 profile...\n", file=sys.stderr)

    results = []
    for i, (username, basic) in enumerate(all_users.items(), 1):
        print(f"  [{i}/{total}] @{username}", file=sys.stderr, end="  ")
        profile, at, rt = fetch_profile(username, at, rt)
        if profile:
            profile["found_via"] = basic.get("found_via", [])
            profile["contact"] = extract_contact(profile["bio"])
            profile["age"] = extract_age(profile["bio"])
            results.append(profile)
            print(f"✓ {profile['screen_name']}", file=sys.stderr)
        else:
            print("✗ 获取失败", file=sys.stderr)
        time.sleep(RATE_LIMIT_DELAY)

    output = json.dumps(results, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"\n已保存 {len(results)} 个用户 profile 到 {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
