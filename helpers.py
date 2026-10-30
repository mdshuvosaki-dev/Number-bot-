import time
from config import OWNER_ID, BASE_URL
from settings import bot_settings
from telegram_api import api_call, send_message, render_body_text
from emojis import PEM


def is_admin(user_id):
    return user_id in bot_settings["admins"] or user_id == OWNER_ID


_fj_cache = {}


def check_force_join(user_id):
    if not bot_settings["fj_on"] or not bot_settings["fj_channels"]: return True
    if is_admin(user_id): return True
    import time as _t
    # সফল হলে ৬০ সেকেন্ড মনে রাখি: প্রতিটি ক্লিকে প্রতিটি চ্যানেল চেক করলে ধীর হয়
    c = _fj_cache.get(user_id)
    if c and _t.time() - c < 60:
        return True
    for ch in bot_settings["fj_channels"]:
        res = api_call("getChatMember", {"chat_id": ch, "user_id": user_id})
        if res.get("ok") and res["result"]["status"] not in ["left", "kicked"]: continue
        else: return False
    _fj_cache[user_id] = _t.time()
    return True


def send_force_join_msg(chat_id):
    kb = []
    for ch in bot_settings["fj_channels"]:
        url = f"https://t.me/{ch.replace('@', '')}" if ch.startswith("@") else ch
        kb.append([{"text": f"Join Channel", "icon_custom_emoji_id": "5789428375261023681", "url": url, "style": "primary"}])
    kb.append([{"text": "Check Joined", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "check_fj", "style": "success"}])
    send_message(chat_id, render_body_text(f"{PEM['warn']} <b>Please join our channels to use the bot!</b>"), reply_markup={"inline_keyboard": kb})
