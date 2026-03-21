import requests
import sys
import json
import os

def get_tenant_access_token(app_id, app_secret):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {
        "app_id": app_id,
        "app_secret": app_secret
    }
    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json().get("tenant_access_token")

def lookup_users(token, emails=None, mobiles=None):
    url = "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "include_resigned": True
    }
    if emails:
        payload["emails"] = emails
    if mobiles:
        payload["mobiles"] = mobiles
        
    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()

if __name__ == "__main__":
    APP_ID = os.environ.get("FEISHU_APP_ID")
    APP_SECRET = os.environ.get("FEISHU_APP_SECRET")
    
    if not APP_ID or not APP_SECRET:
        print("Error: FEISHU_APP_ID and FEISHU_APP_SECRET environment variables must be set.")
        sys.exit(1)
        
    import argparse
    parser = argparse.ArgumentParser(description="Lookup Feishu open_ids by email or mobile.")
    parser.add_argument("--emails", nargs="+", help="One or more emails to lookup")
    parser.add_argument("--mobiles", nargs="+", help="One or more mobile numbers to lookup")
    args = parser.parse_args()
    
    if not args.emails and not args.mobiles:
        print("Error: Provide at least one email or mobile number.")
        sys.exit(1)
        
    try:
        token = get_tenant_access_token(APP_ID, APP_SECRET)
        result = lookup_users(token, emails=args.emails, mobiles=args.mobiles)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)
