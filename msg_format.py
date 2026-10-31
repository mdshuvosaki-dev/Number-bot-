"""
দুটি নতুন মেসেজ ফরম্যাট:
 1) নম্বর অ্যাড করলে সবার কাছে "NEW STOCK ADDED" টেবিল-কার্ড + NUMBER BOT বাটন
 2) নম্বর নিলে "XX Allocated App / Otp Rate / Waiting for OTP / Prefix" মেসেজ + নতুন বাটন সাজানো

টেবিলটি Telegram-এর Rich Message (Bot API 10.1, sendRichMessage) দিয়ে যায়।
কোনো কারণে সেটা না চললে নিজে থেকে সাধারণ মেসেজে (একই লেখা, ব্লককোট) ফিরে যায়।
"""
import re
import time
import html as _html
import threading

import requests

import config as cfg
import settings as S
from emojis import PEM
from telegram_api import render_body_text

FALLBACK_BOT = "MUSTAFIZUR_OTP_3BOT"


def _bot_url():
    uname = (getattr(cfg, "BOT_USERNAME", "") or FALLBACK_BOT).lstrip("@")
    return f"https://t.me/{uname}"


def _emoji_id(emoji_html):
    m = re.search(r'emoji-id="(\d+)"', emoji_html or "")
    return m.group(1) if m else None


# =====================================================================
# 1) NEW STOCK ADDED  (সবার কাছে ব্রডকাস্ট)
# =====================================================================
def _stock_html(country, service, qty, flag_html, app_html):
    c = _html.escape(str(country).upper())
    s = _html.escape(str(service).upper())
    return (
        f"<h3>🔔 NEW STOCK ADDED</h3>"
        f"<table bordered>"
        f"<tr><td>{PEM['world']} COUNTRY</td><td>{flag_html} {c}</td></tr>"
        f"<tr><td>{PEM['phone']} SERVICE</td><td>{app_html} {s}</td></tr>"
        f"<tr><td>{PEM['graph']} QUANTITY</td><td>{qty}</td></tr>"
        f"</table>"
    )


def _stock_fallback(country, service, qty, flag_html, app_html):
    c = _html.escape(str(country).upper())
    s = _html.escape(str(service).upper())
    return render_body_text(
        f"🔔 <b>NEW STOCK ADDED</b>\n\n"
        f"<blockquote>{PEM['world']} <b>COUNTRY</b>   {flag_html} {c}\n"
        f"{PEM['phone']} <b>SERVICE</b>   {app_html} {s}\n"
        f"{PEM['graph']} <b>QUANTITY</b>   {qty}</blockquote>"
    )


def broadcast_new_stock(user_ids, country, service, qty, flag_html, app_html):
    """ব্যাকগ্রাউন্ড থ্রেডে সবাইকে পাঠায়। রিটার্ন নেই।"""
    icon = _emoji_id(flag_html)
    btn = {"text": "NUMBER BOT", "url": _bot_url(), "style": "primary"}
    if icon:
        btn["icon_custom_emoji_id"] = icon
    kb = {"inline_keyboard": [[btn]]}
    rich_html = _stock_html(country, service, qty, flag_html, app_html)
    fb_text = _stock_fallback(country, service, qty, flag_html, app_html)

    def run():
        sess = requests.Session()
        base = f"https://api.telegram.org/bot{cfg.TOKEN}"
        rich_ok = True
        rich_fail_streak = 0
        for uid in list(user_ids):
            sent = False
            if rich_ok:
                try:
                    r = sess.post(f"{base}/sendRichMessage", json={
                        "chat_id": uid, "rich_message": {"html": rich_html}, "reply_markup": kb
                    }, timeout=8).json()
                    if r.get("ok"):
                        sent = True
                        rich_fail_streak = 0
                    else:
                        desc = str(r.get("description", "")).lower()
                        user_side = any(k in desc for k in ("blocked", "deactivated", "chat not found", "forbidden"))
                        if not user_side:
                            rich_fail_streak += 1
                            if rich_fail_streak >= 3:
                                rich_ok = False
                                print(f"⚠️ sendRichMessage unsupported, using normal messages: {r}")
                        else:
                            sent = True  # ইউজার ব্লক করেছে, ফলব্যাকেও যাবে না
                except Exception:
                    pass
            if not sent:
                try:
                    sess.post(f"{base}/sendMessage", json={
                        "chat_id": uid, "text": fb_text, "parse_mode": "HTML",
                        "disable_web_page_preview": True, "reply_markup": kb
                    }, timeout=8)
                except Exception:
                    pass
            time.sleep(0.035)

    threading.Thread(target=run, daemon=True).start()


# =====================================================================
# 2) নম্বর নেওয়ার মেসেজ
# =====================================================================
def build_alloc_view(kb, fetched_nums, country_emoji_html, otp_link):
    """
    পুরনো kb থেকে নতুন লেআউট বানায়:
      নম্বর (সবুজ/লাল পর্যায়ক্রমে) -> কাস্টম বাটন -> OTP Group (সবুজ)
      -> Remove Country Code (নীল) -> [Country] [Change] (নীল)
    রিটার্ন: (text, inline_keyboard)
    """
    from text_utils import get_flag_and_code, get_service_info_html

    svc_name, svc_html = None, ""
    number_rows, custom_rows = [], []
    otp_btn = cc_btn = chg_num = chg_cty = None

    for row in kb:
        if len(row) == 1:
            b = row[0]
            cb = b.get("callback_data", "")
            if "copy_text" in b:
                number_rows.append(b); continue
            if cb == "ignore" and "url" not in b:
                svc_name = b.get("text"); continue
            if cb in ("del_cc_all", "add_cc_all"):
                cc_btn = b; continue
            if cb.startswith("c_n"):
                chg_num = b; continue
            if cb.startswith("g_s_"):
                chg_cty = b; continue
            if b.get("url") and b.get("url") == otp_link and b.get("text") == "OTP Group":
                otp_btn = b; continue
        custom_rows.append(row)

    out = []
    for i, b in enumerate(number_rows):
        nb = dict(b)
        nb["style"] = "success" if i % 2 == 0 else "danger"
        out.append([nb])
    out.extend(custom_rows)
    if otp_btn:
        ob = dict(otp_btn); ob["style"] = "success"
        out.append([ob])
    if cc_btn:
        add = cc_btn.get("callback_data") == "add_cc_all"
        cb2 = dict(cc_btn)
        cb2["text"] = "Add Country Code" if add else "Remove Country Code"
        cb2["style"] = "primary"
        out.append([cb2])
    last = []
    if chg_cty:
        c2 = dict(chg_cty); c2["text"] = "Country"; c2["style"] = "primary"; last.append(c2)
    if chg_num:
        n2 = dict(chg_num); n2["text"] = "Change"; n2["style"] = "primary"; last.append(n2)
    if last:
        out.append(last)

    # ---- হেডার লেখা ----
    first = str(fetched_nums[0]) if fetched_nums else ""
    clean = first.replace("+", "")
    try:
        _, iso = get_flag_and_code(first)
    except Exception:
        iso = ""
    rate = S.assigned_number_rates.get(first)
    if rate is None:
        rate = S.assigned_number_rates.get(clean)
    if rate is None:
        rate = S.bot_settings.get("otp_reward", 0.0)
    prefix = f"{clean[:4]}XXX" if clean else "XXX"

    head = f"{country_emoji_html} <b>{_html.escape(str(iso))}</b> Allocated"
    if svc_name:
        try:
            full, svc_html = get_service_info_html(svc_name)
        except Exception:
            full, svc_html = svc_name, ""
        head += f" {svc_html} <b>{_html.escape(str(full))}</b>"
    text = (f"{head}\n"
            f"{PEM['money']} Otp Rate : <b>{rate} TK</b>\n"
            f"⌛ Waiting for OTP......\n"
            f"{PEM['world']} Prefix: <b>{prefix}</b>")
    return render_body_text(text), out
