import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time

import requests


def gen_sign(timestamp: int, secret: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(hmac_code).decode("utf-8")


def send_message(robot_id: str, secret: str, text: str, at: list[str] | None = None) -> dict:
    url = f"https://open.feishu.cn/open-apis/bot/v2/hook/{robot_id}"
    timestamp = int(time.time())
    at_prefix = "".join(f'<at user_id="{uid}">{uid}</at> ' for uid in at) if at else ""
    payload = {
        "timestamp": str(timestamp),
        "sign": gen_sign(timestamp, secret),
        "msg_type": "text",
        "content": {"text": at_prefix + text},
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()


if __name__ == "__main__":
    robot_id = os.environ.get("FEISHU_ROBOT_ID")
    robot_secret = os.environ.get("FEISHU_ROBOT_SECRET")

    if not robot_id or not robot_secret:
        print("Error: FEISHU_ROBOT_ID and FEISHU_ROBOT_SECRET environment variables must be set.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="通过飞书自定义机器人发送文本消息")
    parser.add_argument("text", help="要发送的消息内容")
    parser.add_argument("--at", nargs="+", metavar="OPEN_ID", help="要 @ 的用户 open_id，可多个")
    args = parser.parse_args()

    try:
        result = send_message(robot_id, robot_secret, args.text, at=args.at)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
