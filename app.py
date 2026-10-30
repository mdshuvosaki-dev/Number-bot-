import time
from concurrent.futures import ThreadPoolExecutor

from config import BOT_USERNAME as _BU
import config as cfg
from telegram_api import api_call, send_message, render_body_text
from emojis import PEM
from database import load_db, sync_users_list
from user_handlers import handle_user_message, handle_user_callback
from admin_handlers import handle_admin_callback
from listeners import (
    panel_monitor_thread, global_sms_listener, stex_console_listener,
    voltx_sms_listener, voltx_console_listener, zenex_sms_listener,
    zenex_console_listener, mint_sms_listener, mint_console_listener
)
import threading
import settings as S


# =========================================================
# UNIFIED CALLBACK ROUTER
# =========================================================
def route_callback(call):
    """Routes callback to admin or user handler."""
    data = call.get("data", "")
    chat_id = call["message"]["chat"]["id"]

    from helpers import is_admin

    # Try admin first (only for private admin users)
    if is_admin(chat_id):
        try:
            handled = handle_admin_callback(call, chat_id, call["message"]["message_id"], data)
            if handled:
                return
        except Exception as e:
            print(f"⚠️ Admin handler error: {e}")

    # Fall through to user handler
    try:
        handle_user_callback(call)
    except Exception as e:
        print(f"⚠️ User handler error: {e}")


# =========================================================
# KEEP-ALIVE WEB SERVER (Render Web Service needs an open port)
# =========================================================
import os
from http.server import BaseHTTPRequestHandler, HTTPServer


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is running")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    print(f"🌐 Web server listening on port {port}")
    server.serve_forever()


def safe_message(msg):
    """handle_user_message এর error লগে দেখানোর জন্য (executor error লুকিয়ে ফেলে)"""
    import traceback
    try:
        print(f"📩 Message from {msg.get('chat', {}).get('id')}: {msg.get('text')}")
        handle_user_message(msg)
    except Exception:
        print("❌ handle_user_message ERROR:\n" + traceback.format_exc())


def safe_callback(call):
    import traceback
    try:
        print(f"🔘 Button: {call.get('data')} from {call.get('from', {}).get('id')}")
        route_callback(call)
    except Exception:
        print("❌ route_callback ERROR:\n" + traceback.format_exc())
    finally:
        # কাজ শেষ, কিন্তু কেউ answer না করলে এখনই করে দিই (বাটনের ঘূর্ণি থামবে)
        try:
            from telegram_api import answer_callback
            answer_callback(call["id"])
        except Exception:
            pass


# =========================================================
# MAIN
# =========================================================
def main():
    # Open a port first so Render's port scan passes
    threading.Thread(target=start_web_server, daemon=True).start()

    # Make print() show up instantly in Render logs
    import sys
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    # Webhook active হলে getUpdates কাজ করে না, তাই আগে মুছে দিচ্ছি
    print("deleteWebhook:", api_call("deleteWebhook", {"drop_pending_updates": False}))

    # Get bot username
    res = api_call("getMe")
    print("getMe:", res)
    if res.get("ok"):
        cfg.BOT_USERNAME = res["result"]["username"]
        # also patch module-level BOT_USERNAME in user_handlers
        import user_handlers
        user_handlers.BOT_USERNAME = cfg.BOT_USERNAME
    print(f"🤖 Bot is starting... @{cfg.BOT_USERNAME}")

    # Load DB
    load_db()

    # Start background threads
    threading.Thread(target=sync_users_list, daemon=True).start()
    threading.Thread(target=panel_monitor_thread, daemon=True).start()
    threading.Thread(target=global_sms_listener, daemon=True).start()
    threading.Thread(target=stex_console_listener, daemon=True).start()
    threading.Thread(target=voltx_sms_listener, daemon=True).start()
    threading.Thread(target=voltx_console_listener, daemon=True).start()
    threading.Thread(target=zenex_sms_listener, daemon=True).start()
    threading.Thread(target=zenex_console_listener, daemon=True).start()
    threading.Thread(target=mint_sms_listener, daemon=True).start()
    threading.Thread(target=mint_console_listener, daemon=True).start()
    print("📡 Background APIs & Global SMS Listener Started!")

    executor = ThreadPoolExecutor(max_workers=500)

    offset = None
    while True:
        try:
            # allowed_updates স্পষ্টভাবে দেওয়া হচ্ছে: আগের কোনো সেটিংয়ে callback_query বাদ
            # থাকলে Telegram সেটাই মনে রাখে, ফলে বাটন ক্লিক কখনো আসে না
            params = {"timeout": 10, "allowed_updates": ["message", "callback_query"]}
            if offset is not None:
                params["offset"] = offset
            updates = api_call("getUpdates", params)
            if updates and updates.get("ok") and "result" in updates:
                for update in updates["result"]:
                    offset = update["update_id"] + 1
                    if "message" in update:
                        executor.submit(safe_message, update["message"])
                    elif "callback_query" in update:
                        executor.submit(safe_callback, update["callback_query"])
            elif not updates:
                time.sleep(1)
            else:
                print(f"⚠️ getUpdates failed: {updates}")
                time.sleep(3)
        except Exception as e:
            print(f"⚠️ Polling error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()
