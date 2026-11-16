"""
WhatsApp / Telegram নম্বর চেকার (DXAZONE Elite Checker API)

Render -> Environment এ দিতে হবে:
  CHECKER_API_KEY     = @WhatChecker_Tgbot থেকে পাওয়া API Key   <-- না দিলে CHECKER বাটন দেখাবে না
ঐচ্ছিক:
  CHECKER_BASE_URL    = ডিফল্ট https://bot.orabitsms.site
  CHECKER_ENABLED     = 0 দিলে চেকার বন্ধ
  CHECKER_MAX_NUMBERS = একবারে সর্বোচ্চ কয়টা নম্বর (ডিফল্ট 10)
  CHECKER_COOLDOWN    = দুই চেকের মাঝে কত সেকেন্ড অপেক্ষা (ডিফল্ট 4)
  CHECKER_DAILY       = প্রতি ইউজার ২৪ ঘণ্টায় সর্বোচ্চ কয়টা নম্বর (ডিফল্ট 100)

গোপনীয়তা: API নম্বরের সাথে নাম/ইউজারনেম/ইউজার আইডি ফেরত দিতে পারে। এই বট সেগুলো
ইউজারকে কখনো দেখায় না, শুধু "রেজিস্টার্ড আছে / নেই" দেখায়।
"""
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor

import requests

from settings import user_states, bot_settings
from helpers import is_admin
from emojis import PEM
from telegram_api import send_message, edit_message, render_body_text

PLATFORMS = {
    "tg": {"label": "Telegram", "path": "/api/check-telegram", "state": "wait_check_tg",
           "free": "🔵", "used": "⚫"},
    "wa": {"label": "WhatsApp", "path": "/api/check-whatsapp", "state": "wait_check_wa",
           "free": "🟢", "used": "🚫"},
}


def _envi(name, default):
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return int(default)


def enabled():
    return bool(os.environ.get("CHECKER_API_KEY")) and os.environ.get("CHECKER_ENABLED", "1") != "0"


# ------------------------------------------------------------------ নম্বর পরিষ্কার
def parse_numbers(text):
    """লাইন/কমা/স্পেস দিয়ে আলাদা নম্বর -> (বৈধ তালিকা, অবৈধ সংখ্যা)।"""
    good, bad, seen = [], 0, set()
    for tok in re.split(r"[\n,;]+", text or ""):
        t = re.sub(r"\D", "", tok)
        if not t:
            if tok.strip():
                bad += 1
            continue
        if t.startswith("00"):
            t = t[2:]
        if 7 <= len(t) <= 15:
            if t not in seen:
                seen.add(t)
                good.append(t)
        else:
            bad += 1
    return good, bad


# ------------------------------------------------------------------ রেট লিমিট
_usage = {}      # uid -> [(timestamp, count)]
_last_call = {}  # uid -> timestamp
_lock = threading.Lock()


def _allowed(uid, n):
    if is_admin(uid):
        return True, ""
    now = time.time()
    cooldown = _envi("CHECKER_COOLDOWN", 4)
    daily = _envi("CHECKER_DAILY", 100)
    with _lock:
        last = _last_call.get(uid, 0)
        if now - last < cooldown:
            return False, f"⏳ Please wait {int(cooldown - (now - last)) + 1}s before the next check."
        rec = [x for x in _usage.get(uid, []) if now - x[0] < 86400]
        used = sum(c for _, c in rec)
        if used + n > daily:
            left = max(0, daily - used)
            return False, f"🚫 Daily limit reached. You can check {left} more number(s) in the next 24 hours."
        rec.append((now, n))
        _usage[uid] = rec
        _last_call[uid] = now
    return True, ""


# ------------------------------------------------------------------ API কল
def _base():
    return os.environ.get("CHECKER_BASE_URL", "https://bot.orabitsms.site").rstrip("/")


def _headers():
    return {"Authorization": f"Bearer {os.environ['CHECKER_API_KEY']}", "Content-Type": "application/json"}


def _check_one(platform, phone, sender=None):
    """রিটার্ন: {"phone", "state": free|used|error, "err": কারণ}"""
    cfg = PLATFORMS[platform]
    payload = {"phone": phone}
    if sender and platform == "wa":
        payload["sender"] = sender
    try:
        r = requests.post(_base() + cfg["path"], json=payload, headers=_headers(), timeout=20)
        if r.status_code == 400 and sender:
            r = requests.post(_base() + cfg["path"], json={"phone": phone}, headers=_headers(), timeout=20)
    except Exception as e:
        print(f"⚠️ checker request failed: {repr(e)[:120]}")
        return {"phone": phone, "state": "error", "err": "network"}
    try:
        j = r.json()
    except Exception:
        return {"phone": phone, "state": "error", "err": f"http{r.status_code}"}
    if r.status_code == 200 and j.get("status") == "ok" and "exists" in j:
        # শুধু exists ব্যবহার হয়; name / username / userId কখনো নেওয়া বা দেখানো হয় না
        return {"phone": phone, "state": "used" if j.get("exists") else "free", "err": ""}
    if r.status_code == 401:
        print("⚠️ checker: API key is wrong or disabled")
        return {"phone": phone, "state": "error", "err": "key"}
    if j.get("whatsappStatus") in ("disconnected", "insufficient_sessions"):
        print("⚠️ checker: no connected WhatsApp session on the API key")
        return {"phone": phone, "state": "error", "err": "wa_offline"}
    print(f"⚠️ checker: unexpected response {r.status_code}: {str(j)[:120]}")
    return {"phone": phone, "state": "error", "err": f"http{r.status_code}"}


# ------------------------------------------------------------------ মেসেজ ও বাটন
def _menu_kb():
    kb = [[{"text": "Telegram", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "chk_tg", "style": "primary"},
           {"text": "WhatsApp", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "chk_wa", "style": "success"}]]
    if os.environ.get("CHECKER_WA_LOGIN", "0") == "1":
        kb.append([{"text": "Link WhatsApp", "icon_custom_emoji_id": "5353022963132174959", "callback_data": "chk_link", "style": "primary"},
                   {"text": "My Account", "icon_custom_emoji_id": "5352552689983067014", "callback_data": "chk_me", "style": "primary"}])
    kb.append([{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}])
    return {"inline_keyboard": kb}


def show_menu(chat_id):
    if not enabled():
        send_message(chat_id, render_body_text("🔎 Number checker is not available right now."))
        return
    maxn = _envi("CHECKER_MAX_NUMBERS", 10)
    send_message(chat_id, render_body_text(
        "━━━━━━━━━━━━━━━\n《 🔎 <b>NUMBER CHECKER</b> 》\n━━━━━━━━━━━━━━━\n"
        "Check if a phone number is already registered on <b>Telegram</b> or <b>WhatsApp</b>.\n"
        f"<i>Up to {maxn} numbers at a time.</i>\n━━━━━━━━━━━━━━━\nChoose a platform:"),
        reply_markup=_menu_kb())


def handle_callback(call):
    """chk_* বাটনগুলোর সব কাজ।"""
    from telegram_api import answer_callback
    chat_id = call["message"]["chat"]["id"]
    msg_id = call["message"]["message_id"]
    data = call.get("data", "")
    if data in ("chk_link", "chk_link_ok", "chk_link_status", "chk_me", "chk_unlink", "chk_unlink_ok"):
        if not enabled() or os.environ.get("CHECKER_WA_LOGIN", "0") != "1":
            answer_callback(call["id"], "This feature is not available right now.", True)
            return
        _link_callback(call, data, chat_id, msg_id)
        return
    key = "tg" if data == "chk_tg" else "wa"
    if not enabled():
        answer_callback(call["id"], "Checker is not available right now.", True)
        return
    cfg = PLATFORMS[key]
    user_states[chat_id] = cfg["state"]
    maxn = _envi("CHECKER_MAX_NUMBERS", 10)
    cancel = {"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176",
                                    "callback_data": "cancel_state", "style": "danger"}]]}
    edit_message(chat_id, msg_id, render_body_text(
        f"━━━━━━━━━━━━━━━\n《 🔎 <b>{cfg['label'].upper()} CHECK</b> 》\n━━━━━━━━━━━━━━━\n"
        f"📝 Send the number(s) with country code, one per line (max {maxn}):\n"
        "<code>8801712345678\n447911123456</code>"), reply_markup=cancel)
    answer_callback(call["id"])


def handle_input(chat_id, state, text):
    """ইউজার নম্বর পাঠালে চেক করে ফল দেয়। state বজায় থাকে, তাই আবার নম্বর পাঠানো যায়।"""
    if state == "wait_link_phone":
        _link_phone_input(chat_id, text)
        return
    key = "tg" if state == "wait_check_tg" else "wa"
    cfg = PLATFORMS[key]
    if not enabled():
        user_states.pop(chat_id, None)
        send_message(chat_id, render_body_text("🔎 Number checker is not available right now."))
        return
    maxn = _envi("CHECKER_MAX_NUMBERS", 10)
    nums, bad = parse_numbers(text)
    cancel = {"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176",
                                    "callback_data": "cancel_state", "style": "danger"}]]}
    if not nums:
        send_message(chat_id, render_body_text(
            "❌ No valid number found. Send numbers with country code (7–15 digits), one per line."), reply_markup=cancel)
        return
    if len(nums) > maxn:
        send_message(chat_id, render_body_text(
            f"❌ Too many numbers ({len(nums)}). Send at most {maxn} at a time."), reply_markup=cancel)
        return
    ok, why = _allowed(chat_id, len(nums))
    if not ok:
        send_message(chat_id, render_body_text(why), reply_markup=cancel)
        return

    res = send_message(chat_id, render_body_text(f"⌛ Checking {len(nums)} number(s) on {cfg['label']}..."))
    try:
        mid = res["result"]["message_id"]
    except Exception:
        mid = None

    sender = _linked(chat_id) if key == "wa" else None
    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(lambda n: _check_one(key, n, sender), nums))

    errs = {r["err"] for r in results if r["state"] == "error"}
    if len(errs) and all(r["state"] == "error" for r in results):
        reason = "The checker service is temporarily unavailable. Please try again later."
        if "wa_offline" in errs:
            reason = "WhatsApp checker is offline right now. Please try again later."
        final = f"❌ {reason}"
    else:
        lines, free, used, failed = [], 0, 0, 0
        for r in results:
            if r["state"] == "free":
                free += 1
                lines.append(f"{cfg['free']} <code>+{r['phone']}</code> — <b>Not registered</b>")
            elif r["state"] == "used":
                used += 1
                lines.append(f"{cfg['used']} <code>+{r['phone']}</code> — <b>Registered</b>")
            else:
                failed += 1
                lines.append(f"⚠️ <code>+{r['phone']}</code> — check failed")
        summary = f"{cfg['free']} Not registered: <b>{free}</b>   {cfg['used']} Registered: <b>{used}</b>"
        if failed:
            summary += f"   ⚠️ Failed: <b>{failed}</b>"
        final = (f"━━━━━━━━━━━━━━━\n《 🔎 <b>{cfg['label'].upper()} RESULT</b> 》\n━━━━━━━━━━━━━━━\n"
                 + "\n".join(lines) + f"\n━━━━━━━━━━━━━━━\n{summary}")
        if bad:
            final += f"\n<i>{bad} invalid entry(s) skipped.</i>"
        final += "\n\n📝 Send more numbers to check again."

    kb = {"inline_keyboard": [
        [{"text": "Telegram", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "chk_tg", "style": "primary"},
         {"text": "WhatsApp", "icon_custom_emoji_id": "5352694861990501856", "callback_data": "chk_wa", "style": "success"}],
        [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507", "callback_data": "close_msg", "style": "danger"}]]}
    if mid:
        edit_message(chat_id, mid, render_body_text(final), reply_markup=kb)
    else:
        send_message(chat_id, render_body_text(final), reply_markup=kb)



# =====================================================================
# WhatsApp লগইন (লিংক): ইউজার নিজের WhatsApp পেয়ারিং কোড দিয়ে যুক্ত করে
# শুধু CHECKER_WA_LOGIN=1 দিলে চালু হয়; ডিফল্টে বন্ধ, কারণ এতে ইউজারের
# WhatsApp সেশন তৃতীয় পক্ষের API সার্ভারে যায়।
# =====================================================================
_link_attempts = {}


def _accounts():
    return bot_settings.setdefault("checker_accounts", {})


def _linked(uid):
    return _accounts().get(str(uid))


def _save():
    try:
        from database import save_db
        save_db()
    except Exception:
        pass


def _mask(phone):
    p = str(phone)
    return p[:4] + "•" * max(0, len(p) - 7) + p[-3:] if len(p) > 7 else p


def _session_state(phone):
    try:
        r = requests.get(_base() + "/api/user-status", headers=_headers(), timeout=20)
        j = r.json()
    except Exception:
        return None
    for s in (j.get("ActiveSessions") or []):
        if str(s.get("phone", "")).replace("+", "") == str(phone):
            return True
    for s in (j.get("DisconnectedSessions") or []):
        if str(s.get("phone", "")).replace("+", "") == str(phone):
            return False
    return False if r.status_code == 200 else None


CONSENT = (
    "━━━━━━━━━━━━━━━\n《 🔗 <b>LINK YOUR WHATSAPP</b> 》\n━━━━━━━━━━━━━━━\n"
    "Linking works like WhatsApp Web: the checker service keeps a <b>linked-device session</b> "
    "of your WhatsApp on its server and uses it only to look up whether numbers are registered.\n\n"
    "⚠️ <b>Please read:</b>\n"
    "• Use a <b>spare number</b>, not your main WhatsApp.\n"
    "• A linked session can technically access that account, so link only if you accept this.\n"
    "• WhatsApp may restrict accounts used for many lookups.\n"
    "• You can unlink any time: WhatsApp → Settings → Linked devices → log out the device.\n"
    "━━━━━━━━━━━━━━━")


def _link_callback(call, data, chat_id, msg_id):
    from telegram_api import answer_callback
    uid = chat_id

    if data == "chk_link":
        kb = {"inline_keyboard": [
            [{"text": "I understand, continue", "icon_custom_emoji_id": "5352694861990501856",
              "callback_data": "chk_link_ok", "style": "success"}],
            [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176",
              "callback_data": "cancel_state", "style": "danger"}]]}
        edit_message(chat_id, msg_id, render_body_text(CONSENT), reply_markup=kb)
        answer_callback(call["id"])
        return

    if data == "chk_link_ok":
        now = time.time()
        recent = [t for t in _link_attempts.get(uid, []) if now - t < 86400]
        if len(recent) >= _envi("CHECKER_LINK_DAILY", 3) and not is_admin(uid):
            answer_callback(call["id"], "Too many link attempts today. Try again tomorrow.", True)
            return
        user_states[uid] = "wait_link_phone"
        edit_message(chat_id, msg_id, render_body_text(
            "📝 Send the <b>WhatsApp number</b> you want to link, with country code.\n"
            "Example: <code>8801700000000</code>"),
            reply_markup={"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176",
                                                "callback_data": "cancel_state", "style": "danger"}]]})
        answer_callback(call["id"])
        return

    if data == "chk_link_status":
        phone = _linked_pending.get(uid)
        if not phone:
            answer_callback(call["id"], "No pending link. Start again from Link WhatsApp.", True)
            return
        st = _session_state(phone)
        if st:
            _accounts()[str(uid)] = phone
            _linked_pending.pop(uid, None)
            _save()
            edit_message(chat_id, msg_id, render_body_text(
                f"✅ <b>WhatsApp linked!</b>\n📱 <code>+{_mask(phone)}</code>\n\n"
                "Your WhatsApp checks will now use this account."), reply_markup=_menu_kb())
            answer_callback(call["id"])
        elif st is None:
            answer_callback(call["id"], "Could not check right now. Try again in a moment.", True)
        else:
            answer_callback(call["id"], "Not connected yet. Enter the code in WhatsApp, then tap again.", True)
        return

    if data == "chk_me":
        phone = _linked(uid)
        if not phone:
            txt = ("👤 <b>MY ACCOUNT</b>\n\nNo WhatsApp linked yet.\n"
                   "Tap <b>Link WhatsApp</b> to add yours. Telegram checks need no login.")
            kb = _menu_kb()
        else:
            st = _session_state(phone)
            label = "🟢 Connected" if st else ("🔴 Disconnected" if st is False else "⚪ Unknown")
            txt = (f"👤 <b>MY ACCOUNT</b>\n\n📱 WhatsApp: <code>+{_mask(phone)}</code>\n"
                   f"Status: {label}\n\nTo fully unlink, log out the device in "
                   "WhatsApp → Settings → Linked devices.")
            kb = {"inline_keyboard": [
                [{"text": "Remove from bot", "icon_custom_emoji_id": "5420130255174145507",
                  "callback_data": "chk_unlink", "style": "danger"}],
                [{"text": "Close", "icon_custom_emoji_id": "5420130255174145507",
                  "callback_data": "close_msg", "style": "primary"}]]}
        edit_message(chat_id, msg_id, render_body_text(txt), reply_markup=kb)
        answer_callback(call["id"])
        return

    if data == "chk_unlink":
        kb = {"inline_keyboard": [
            [{"text": "Yes, remove", "icon_custom_emoji_id": "5420130255174145507",
              "callback_data": "chk_unlink_ok", "style": "danger"},
             {"text": "No", "icon_custom_emoji_id": "5267490665117275176",
              "callback_data": "chk_me", "style": "primary"}]]}
        edit_message(chat_id, msg_id, render_body_text(
            "Remove your WhatsApp from this bot?\n<i>This does not log the device out of WhatsApp. "
            "Do that yourself in WhatsApp → Linked devices.</i>"), reply_markup=kb)
        answer_callback(call["id"])
        return

    if data == "chk_unlink_ok":
        _accounts().pop(str(uid), None)
        _save()
        edit_message(chat_id, msg_id, render_body_text("✅ Removed from this bot."), reply_markup=_menu_kb())
        answer_callback(call["id"])
        return


_linked_pending = {}


def _link_phone_input(chat_id, text):
    uid = chat_id
    nums, _bad = parse_numbers(text)
    cancel = {"inline_keyboard": [[{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176",
                                    "callback_data": "cancel_state", "style": "danger"}]]}
    if len(nums) != 1:
        send_message(chat_id, render_body_text(
            "❌ Send exactly one number with country code, e.g. <code>8801700000000</code>"), reply_markup=cancel)
        return
    phone = nums[0]
    now = time.time()
    recent = [t for t in _link_attempts.get(uid, []) if now - t < 86400]
    if len(recent) >= _envi("CHECKER_LINK_DAILY", 3) and not is_admin(uid):
        user_states.pop(uid, None)
        send_message(chat_id, render_body_text("🚫 Too many link attempts today. Try again tomorrow."))
        return
    recent.append(now)
    _link_attempts[uid] = recent

    res = send_message(chat_id, render_body_text("⌛ Requesting your pairing code..."))
    try:
        mid = res["result"]["message_id"]
    except Exception:
        mid = None
    try:
        r = requests.post(_base() + "/api/connect-whatsapp", json={"phone": phone}, headers=_headers(), timeout=30)
        j = r.json()
    except Exception as e:
        print(f"⚠️ checker connect failed: {repr(e)[:120]}")
        j, r = {}, None
    user_states.pop(uid, None)
    code = j.get("pairingCode") if isinstance(j, dict) else None
    if r is not None and r.status_code == 200 and j.get("success") and code:
        _linked_pending[uid] = phone
        txt = ("━━━━━━━━━━━━━━━\n《 🔗 <b>PAIRING CODE</b> 》\n━━━━━━━━━━━━━━━\n"
               f"📱 Number: <code>+{phone}</code>\n🔑 Code: <code>{code}</code>\n━━━━━━━━━━━━━━━\n"
               "1) Open WhatsApp on that phone\n2) Settings → <b>Linked devices</b> → <b>Link a device</b>\n"
               "3) Choose <b>Link with phone number instead</b>\n4) Enter the code above\n\n"
               "Then tap the button below.")
        kb = {"inline_keyboard": [
            [{"text": "Copy code", "icon_custom_emoji_id": "5353022963132174959", "copy_text": {"text": code}, "style": "primary"}],
            [{"text": "I entered the code", "icon_custom_emoji_id": "5352694861990501856",
              "callback_data": "chk_link_status", "style": "success"}],
            [{"text": "Cancel", "icon_custom_emoji_id": "5267490665117275176",
              "callback_data": "cancel_state", "style": "danger"}]]}
    else:
        if r is not None:
            print(f"⚠️ checker connect: {r.status_code} {str(j)[:120]}")
        txt = "❌ Could not create a pairing code right now. Please try again later."
        kb = _menu_kb()
    if mid:
        edit_message(chat_id, mid, render_body_text(txt), reply_markup=kb)
    else:
        send_message(chat_id, render_body_text(txt), reply_markup=kb)
