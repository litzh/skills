#!/usr/bin/env python3
"""飞书 CLI 工具集"""

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time

import requests


# ── 公共 ──────────────────────────────────────────────────────────────────────

def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": app_id, "app_secret": app_secret})
    resp.raise_for_status()
    return resp.json()["tenant_access_token"]


# ── batch-get-id ──────────────────────────────────────────────────────────────

def cmd_batch_get_id(args) -> None:
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        print("Error: FEISHU_APP_ID and FEISHU_APP_SECRET must be set.", file=sys.stderr)
        sys.exit(1)

    if not args.emails and not args.mobiles:
        print("Error: provide at least one --emails or --mobiles.", file=sys.stderr)
        sys.exit(1)

    token = get_tenant_access_token(app_id, app_secret)
    url = "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id"
    payload: dict = {"include_resigned": True}
    if args.emails:
        payload["emails"] = args.emails
    if args.mobiles:
        payload["mobiles"] = args.mobiles

    resp = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
    resp.raise_for_status()
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))


# ── robot-send ────────────────────────────────────────────────────────────────

def _gen_sign(timestamp: int, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def cmd_robot_send(args) -> None:
    robot_id = os.environ.get("FEISHU_ROBOT_ID")
    robot_secret = os.environ.get("FEISHU_ROBOT_SECRET")
    if not robot_id or not robot_secret:
        print("Error: FEISHU_ROBOT_ID and FEISHU_ROBOT_SECRET must be set.", file=sys.stderr)
        sys.exit(1)

    timestamp = int(time.time())
    at_prefix = "".join(f'<at user_id="{uid}">{uid}</at> ' for uid in args.at) if args.at else ""
    payload = {
        "timestamp": str(timestamp),
        "sign": _gen_sign(timestamp, robot_secret),
        "msg_type": "text",
        "content": {"text": at_prefix + args.text},
    }
    resp = requests.post(f"https://open.feishu.cn/open-apis/bot/v2/hook/{robot_id}", json=payload)
    resp.raise_for_status()
    print(json.dumps(resp.json(), indent=2, ensure_ascii=False))


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(prog="feishu", description="飞书 API 工具集")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # batch-get-id
    p_get = sub.add_parser("batch-get-id", help="通过邮箱或手机号查询 open_id")
    p_get.add_argument("--emails", nargs="+", metavar="EMAIL", help="邮箱列表")
    p_get.add_argument("--mobiles", nargs="+", metavar="MOBILE", help="手机号列表")
    p_get.set_defaults(func=cmd_batch_get_id)

    # robot-send
    p_send = sub.add_parser("robot-send", help="通过自定义机器人发送消息")
    p_send.add_argument("text", help="消息内容")
    p_send.add_argument("--at", nargs="+", metavar="OPEN_ID", help="@ 的用户 open_id")
    p_send.set_defaults(func=cmd_robot_send)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
