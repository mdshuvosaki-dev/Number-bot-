"""
USDT (BEP20 / BNB Smart Chain) অটো পেআউট — Bitget API দিয়ে।

Render -> Environment এ এগুলো দিতে হবে:
  USDT_RATE_TK        = ১ USDT = কত টাকা (যেমন 125)   <-- না দিলে USDT অপশন দেখাবে না
  BITGET_API_KEY      = Bitget API key   (শুধু Withdraw অনুমতি + IP whitelist)
  BITGET_API_SECRET   = Bitget secret
  BITGET_PASSPHRASE   = Bitget passphrase
ঐচ্ছিক:
  USDT_AUTO           = 0 দিলে অটো বন্ধ (সব অনুরোধে অ্যাডমিনের APPROVE লাগবে), ডিফল্ট 1
  USDT_AUTO_MAX       = এর বেশি অঙ্কে অ্যাডমিন অনুমোদন লাগবে (USDT), ডিফল্ট 10
  USDT_DAILY_USER     = প্রতি ইউজার ২৪ ঘণ্টায় অটো সীমা (USDT), ডিফল্ট 20
  USDT_DAILY_TOTAL    = মোট ২৪ ঘণ্টায় অটো সীমা (USDT), ডিফল্ট 100
  USDT_MIN_NET        = ফি কাটার পর ন্যূনতম যা ইউজার পাবে (USDT), ডিফল্ট 1
  USDT_FEE            = Bitget থেকে ফি আনতে না পারলে ব্যবহৃত ফি (USDT), ডিফল্ট 1
  QUOTAGUARDSTATIC_URL (বা BITGET_PROXY_URL) = স্থির IP প্রক্সির URL; Bitget এ শুধু ওই IP whitelist হবে
"""
import os
import re
import time
import math
import uuid
import hmac
import json
import base64
import hashlib
import threading

import requests

from config import db
from settings import pending_withdrawals, bot_settings, user_states, temp_data
from telegram_api import send_message, edit_message, render_body_text
from database import update_balance, get_user
from emojis import PEM

try:
    from firebase_admin import firestore
except Exception:
    firestore = None

USDT_METHOD = "USDT (BEP20)"
BITGET_BASE = "https://api.bitget.com"
WITHDRAW_PATH = "/api/v2/spot/wallet/withdrawal"
COINS_PATH = "/api/v2/spot/public/coins"


# ---------------------------------------------------------------- env helpers
def _envf(name, default):
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return float(default)


def usdt_enabled():
    """USDT_RATE_TK সেট না থাকলে USDT অপশন দেখানো হবে না (ভুল রেটে টাকা যাওয়া ঠেকাতে)।"""
    try:
        return float(os.environ.get("USDT_RATE_TK", "0")) > 0
    except Exception:
        return False


def rate_tk():
    return float(os.environ.get("USDT_RATE_TK", "0"))


def has_keys():
    return all(os.environ.get(k) for k in ("BITGET_API_KEY", "BITGET_API_SECRET", "BITGET_PASSPHRASE"))


def auto_enabled():
    return has_keys() and os.environ.get("USDT_AUTO", "1") != "0"


# ---------------------------------------------------------------- fee / calc
_fee_cache = {"t": 0, "fee": None, "min": 0.0, "chain": None}


def _load_chain_info():
    now = time.time()
    if _fee_cache["fee"] is not None and now - _fee_cache["t"] < 600:
        return
    try:
        r = requests.get(BITGET_BASE + COINS_PATH, params={"coin": "USDT"}, timeout=10).json()
        for coin in r.get("data", []) or []:
            for ch in coin.get("chains", []) or []:
                if str(ch.get("chain", "")).upper() in ("BEP20", "BSC", "BNB SMART CHAIN"):
                    _fee_cache.update({
                        "t": now,
                        "fee": float(ch.get("withdrawFee")),
                        "min": float(ch.get("minWithdrawAmount") or 0),
                        "chain": ch.get("chain"),
                    })
                    return
    except Exception as e:
        print(f"⚠️ Bitget fee fetch failed: {repr(e)[:150]}")


def get_fee():
    _load_chain_info()
    if _fee_cache["fee"] is not None:
        return _fee_cache["fee"]
    return _envf("USDT_FEE", 1.0)


def get_chain():
    _load_chain_info()
    return _fee_cache["chain"] or os.environ.get("BITGET_CHAIN", "BEP20")


def _floor4(x):
    return math.floor(x * 10000) / 10000


def calc_usdt(amount_tk):
    """ইউজারের টাকা -> USDT; ফি কেটে নিয়ে ইউজার যত পাবে (net)।"""
    gross = _floor4(amount_tk / rate_tk())
    fee = get_fee()
    net = _floor4(gross - fee)
    _load_chain_info()
    min_net = max(_envf("USDT_MIN_NET", 1.0), _fee_cache["min"] or 0.0)
    return {"gross": gross, "fee": fee, "net": net, "min_net": min_net, "rate": rate_tk()}


def min_tk_for_usdt():
    """ফি কাটার পরও ন্যূনতম পরিমাণ পেতে ইউজারকে কমপক্ষে কত টাকা তুলতে হবে।"""
    c = calc_usdt(0)
    return math.ceil((c["min_net"] + c["fee"]) * rate_tk())


def is_valid_bep20(addr):
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", addr or ""):
        return False
    return int(addr, 16) != 0


# ---------------------------------------------------------------- limits
_recent = []  # (timestamp, user_id, net)
_lock = threading.Lock()


def within_limits(user_id, net):
    auto_max = _envf("USDT_AUTO_MAX", 10)
    per_user = _envf("USDT_DAILY_USER", 20)
    total_cap = _envf("USDT_DAILY_TOTAL", 100)
    if net > auto_max:
        return False
    cutoff = time.time() - 86400
    with _lock:
        _recent[:] = [x for x in _recent if x[0] >= cutoff]
        user_sum = sum(x[2] for x in _recent if x[1] == user_id)
        total_sum = sum(x[2] for x in _recent)
    return (user_sum + net <= per_user) and (total_sum + net <= total_cap)


def _record(user_id, net):
    with _lock:
        _recent.append((time.time(), user_id, net))


# ---------------------------------------------------------------- Bitget call
def _sign(secret, ts, method, path, body):
    msg = f"{ts}{method.upper()}{path}{body}"
    return base64.b64encode(hmac.new(secret.encode(), msg.encode(), hashlib.sha256).digest()).decode()


def bitget_withdraw(client_oid, address, net):
    """
    রিটার্ন: ("ok", orderId) | ("fail", কারণ) | ("unknown", কারণ)
    unknown = নেটওয়ার্ক সমস্যা, টাকা গেছে কি না নিশ্চিত নয় -> রিফান্ড করা হয় না, অ্যাডমিন যাচাই করবে।
    """
    body_obj = {
        "coin": "USDT",
        "transferType": "on_chain",
        "address": address,
        "chain": get_chain(),
        "size": f"{net:.4f}",
        "clientOid": client_oid,
    }
    body = json.dumps(body_obj, separators=(",", ":"))
    ts = str(int(time.time() * 1000))
    headers = {
        "ACCESS-KEY": os.environ["BITGET_API_KEY"],
        "ACCESS-SIGN": _sign(os.environ["BITGET_API_SECRET"], ts, "POST", WITHDRAW_PATH, body),
        "ACCESS-TIMESTAMP": ts,
        "ACCESS-PASSPHRASE": os.environ["BITGET_PASSPHRASE"],
        "Content-Type": "application/json",
        "locale": "en-US",
    }
    # স্থির IP-র জন্য প্রক্সি (যেমন QuotaGuard): Render Environment এ QUOTAGUARDSTATIC_URL দিলে
    # শুধু Bitget উইথড্র কল ওই প্রক্সি দিয়ে যাবে, তাই Bitget এ শুধু প্রক্সির IP whitelist করলেই চলে
    proxy_url = os.environ.get("QUOTAGUARDSTATIC_URL") or os.environ.get("BITGET_PROXY_URL")
    proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
    try:
        r = requests.post(BITGET_BASE + WITHDRAW_PATH, headers=headers, data=body, timeout=20, proxies=proxies)
    except Exception as e:
        return "unknown", repr(e)[:150]
    if r.status_code >= 500:
        return "unknown", f"HTTP {r.status_code}"
    try:
        j = r.json()
    except Exception:
        return "unknown", f"HTTP {r.status_code} (invalid response)"
    if str(j.get("code")) == "00000":
        return "ok", str((j.get("data") or {}).get("orderId", ""))
    return "fail", f"{j.get('code')}: {j.get('msg')}"


# ---------------------------------------------------------------- Firestore log
def _fs_update(req_id, data):
    if not db:
        return
    try:
        db.collection("withdrawals").document(req_id).update(data)
    except Exception:
        pass


def _group(text, kb=None):
    g = bot_settings.get("w_group")
    if g:
        send_message(g, render_body_text(text), reply_markup=kb)


def _status_kb(label, ok):
    icon = "5352694861990501856" if ok else "5420130255174145507"
    return {"inline_keyboard": [[{"text": label, "icon_custom_emoji_id": icon,
                                  "callback_data": "ignore", "style": "success" if ok else "danger"}]]}


def _summary(req_id, req, title):
    u = req["usdt"]
    return (f"🎙 <b>{title}</b>\n\n"
            f"👤 <b>USER:</b> <a href='tg://user?id={req['user_id']}'>{req.get('full_name', req['user_id'])}</a>\n"
            f"💳 <b>AMOUNT:</b> {req['amount']} TK\n"
            f"💱 <b>RATE:</b> 1 USDT = {u['rate']} TK\n"
            f"💸 <b>FEE:</b> {u['fee']:.4f} USDT\n"
            f"✅ <b>SEND:</b> <code>{u['net']:.4f}</code> USDT (BEP20)\n"
            f"📥 <b>ADDRESS:</b> <code>{req['number']}</code>\n\n"
            f"🧾 <b>REQ ID:</b> {req_id}")


# ---------------------------------------------------------------- payout
def process_payout(req_id, admin_chat=None, admin_msg=None):
    """অনুরোধ পেন্ডিং থেকে তুলে একবারই পাঠানো হয় (দ্বিতীয়বার ক্লিকে কিছু হবে না)।"""
    req = pending_withdrawals.pop(req_id, None)
    if not req:
        return
    uid, amount, addr, u = req["user_id"], req["amount"], req["number"], req["usdt"]

    def show(title, label, ok):
        text = _summary(req_id, req, title)
        if admin_chat and admin_msg:
            edit_message(admin_chat, admin_msg, render_body_text(text), reply_markup=_status_kb(label, ok))
        else:
            _group(text, _status_kb(label, ok))

    # কী না থাকলে ম্যানুয়াল মোড: অ্যাডমিন নিজে পাঠিয়ে APPROVE চেপেছে
    if not has_keys():
        _fs_update(req_id, {"status": "approved", "usdt_net": u["net"], "address": addr})
        show("USDT WITHDRAWAL APPROVED", "APPROVED", True)
        send_message(uid, render_body_text(
            f"{PEM['ok']} Your USDT withdrawal has been paid!\n\n"
            f"💰 <b>Received:</b> {u['net']:.4f} USDT (BEP20)\n📥 <b>Address:</b> <code>{addr}</code>"))
        return

    status, info = bitget_withdraw(req_id, addr, u["net"])

    if status == "ok":
        _record(uid, u["net"])
        _fs_update(req_id, {"status": "approved", "usdt_net": u["net"], "address": addr, "order_id": info})
        show("USDT PAID", "PAID", True)
        send_message(uid, render_body_text(
            f"{PEM['ok']} Your USDT withdrawal was sent!\n\n"
            f"💰 <b>Withdrawn:</b> {amount} ৳ ({u['gross']:.4f} USDT)\n"
            f"💸 <b>Network fee:</b> {u['fee']:.4f} USDT\n"
            f"✅ <b>You receive:</b> {u['net']:.4f} USDT (BEP20)\n"
            f"📥 <b>Address:</b> <code>{addr}</code>\n"
            f"🧾 <b>Order:</b> {info}"))
    elif status == "fail":
        update_balance(uid, amount)  # নিশ্চিত ব্যর্থ -> ব্যালেন্স ফেরত
        _fs_update(req_id, {"status": "failed", "error": info})
        show("USDT FAILED (REFUNDED)", "FAILED", False)
        _group(f"⚠️ <b>USDT payout failed</b> (user refunded)\n🧾 {req_id}\n❗ {info}")
        send_message(uid, render_body_text(
            f"❌ Your USDT withdrawal could not be processed. {amount} ৳ has been refunded to your balance."))
    else:
        # নিশ্চিত নয়: রিফান্ড করা হয়নি, ডাবল-পেমেন্ট এড়াতে
        _fs_update(req_id, {"status": "unknown", "error": info})
        show("USDT CHECK NEEDED", "CHECK BITGET", False)
        _group(f"⚠️ <b>USDT payout status UNKNOWN</b> — balance NOT refunded.\n"
               f"Check Bitget withdrawal records for clientOid <code>{req_id}</code>.\n❗ {info}")
        send_message(uid, render_body_text(
            "⏳ Your USDT withdrawal is being checked. You will be notified shortly."))


# ---------------------------------------------------------------- user request
def submit_usdt_request(chat_id, msg, msg_id, amount, text):
    from keyboards import get_cancel_kb

    def say(t, kb=None):
        if msg_id:
            edit_message(chat_id, msg_id, render_body_text(t), reply_markup=kb)
        else:
            send_message(chat_id, render_body_text(t), reply_markup=kb)

    address = (text or "").strip()
    if not is_valid_bep20(address):
        say("❌ Invalid address!\n\nSend a valid <b>BEP20 (BNB Smart Chain)</b> USDT address "
            "(starts with <code>0x</code>, 42 characters):", get_cancel_kb())
        return

    bal = get_user(chat_id).get("balance", 0.0)
    c = calc_usdt(amount)
    if amount > bal or c["net"] < c["min_net"]:
        user_states.pop(chat_id, None)
        temp_data.pop(chat_id, None)
        say("❌ Request could not be created (balance changed or amount too small). Please try again.")
        return

    first = msg.get("from", {}).get("first_name", "User")
    last = msg.get("from", {}).get("last_name", "")
    full_name = f"{first} {last}".strip()
    req_id = f"W_{str(uuid.uuid4())[:6].upper()}"

    update_balance(chat_id, -amount)
    req = {"user_id": chat_id, "amount": amount, "method": USDT_METHOD, "number": address,
           "full_name": full_name, "usdt": c}
    pending_withdrawals[req_id] = req

    if db:
        try:
            db.collection("withdrawals").document(req_id).set({
                "user_id": str(chat_id), "amount": amount, "method": USDT_METHOD, "status": "pending",
                "usdt_net": c["net"], "usdt_fee": c["fee"], "address": address,
                "timestamp": firestore.SERVER_TIMESTAMP if firestore else None,
            })
        except Exception:
            pass

    auto = auto_enabled() and within_limits(chat_id, c["net"])

    if auto:
        _group(_summary(req_id, req, "NEW USDT WITHDRAWAL (AUTO)"))
    else:
        kb = {"inline_keyboard": [[
            {"text": "APPROVE", "icon_custom_emoji_id": "5352694861990501856",
             "callback_data": f"wapp_{req_id}", "style": "success"},
            {"text": "REJECT", "icon_custom_emoji_id": "5420130255174145507",
             "callback_data": f"wrej_{req_id}", "style": "danger"}]]}
        _group(_summary(req_id, req, "NEW USDT WITHDRAWAL"), kb)

    note = "⏳ Sending your USDT now..." if auto else "⏳ Waiting for admin approval."
    close_kb = {"inline_keyboard": [[{"text": "Close", "icon_custom_emoji_id": "5420130255174145507",
                                      "callback_data": "close_msg", "style": "danger"}]]}
    say(f"{PEM['ok']} Your USDT withdrawal request has been submitted!\n\n"
        f"🧾 <b>Req ID:</b> {req_id}\n"
        f"💰 <b>Amount:</b> {amount} ৳ ({c['gross']:.4f} USDT)\n"
        f"💸 <b>Network fee:</b> {c['fee']:.4f} USDT\n"
        f"✅ <b>You receive:</b> {c['net']:.4f} USDT (BEP20)\n"
        f"📥 <b>Address:</b> <code>{address}</code>\n\n{note}", close_kb)

    user_states.pop(chat_id, None)
    temp_data.pop(chat_id, None)

    if auto:
        threading.Thread(target=process_payout, args=(req_id,), daemon=True).start()
