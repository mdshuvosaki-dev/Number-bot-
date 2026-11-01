"""
দুটি নতুন মেসেজ ফরম্যাট:
 1) নম্বর অ্যাড করলে সবার কাছে "NEW STOCK ADDED" টেবিল-কার্ড + NUMBER BOT বাটন
 2) নম্বর নিলে "XX Allocated App / Otp Rate / Waiting for OTP / Prefix" মেসেজ + নতুন বাটন সাজানো

টেবিলটি Telegram-এর Rich Message (Bot API 10.1, sendRichMessage) দিয়ে যায়।
কোনো কারণে সেটা না চললে নিজে থেকে সাধারণ মেসেজে (একই লেখা, ব্লককোট) ফিরে যায়।
"""
import re
import os
import time
import base64
import uuid
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
# বাঁদিকের আইকন বদলাতে চাইলে এখানে প্রিমিয়াম ইমোজি বসান, যেমন:
#   ICON_SERVICE = '<tg-emoji emoji-id="আইডি">🤖</tg-emoji>'
ICON_BELL = '<tg-emoji emoji-id="5352980533150259581">🔔</tg-emoji>'
ICON_COUNTRY = PEM["world"]
ICON_SERVICE = '<tg-emoji emoji-id="5337132498965010628">📱</tg-emoji>'
ICON_QUANTITY = '<tg-emoji emoji-id="5352877703043258544">📈</tg-emoji>'
DEFAULT_BTN_ICON_ID = "5336972142066047577"   # ফ্ল্যাগের প্রিমিয়াম আইডি না থাকলে বাটনে এই আইকন

ISO_NAMES = {
    "AC": "Ascension Island", "AD": "Andorra", "AE": "United Arab Emirates", "AF": "Afghanistan",
    "AG": "Antigua & Barbuda", "AI": "Anguilla", "AL": "Albania", "AM": "Armenia",
    "AO": "Angola", "AQ": "Antarctica", "AR": "Argentina", "AS": "American Samoa",
    "AT": "Austria", "AU": "Australia", "AW": "Aruba", "AX": "Åland Islands",
    "AZ": "Azerbaijan", "BA": "Bosnia & Herzegovina", "BB": "Barbados", "BD": "Bangladesh",
    "BE": "Belgium", "BF": "Burkina Faso", "BG": "Bulgaria", "BH": "Bahrain",
    "BI": "Burundi", "BJ": "Benin", "BL": "St. Barthélemy", "BM": "Bermuda",
    "BN": "Brunei", "BO": "Bolivia", "BQ": "Caribbean Netherlands", "BR": "Brazil",
    "BS": "Bahamas", "BT": "Bhutan", "BV": "Bouvet Island", "BW": "Botswana",
    "BY": "Belarus", "BZ": "Belize", "CA": "Canada", "CC": "Cocos (Keeling) Islands",
    "CD": "DR Congo", "CF": "Central African Republic", "CG": "Congo", "CH": "Switzerland",
    "CI": "Ivory Coast", "CK": "Cook Islands", "CL": "Chile", "CM": "Cameroon",
    "CN": "China", "CO": "Colombia", "CP": "Clipperton Island", "CQ": "Sark",
    "CR": "Costa Rica", "CU": "Cuba", "CV": "Cape Verde", "CW": "Curaçao",
    "CX": "Christmas Island", "CY": "Cyprus", "CZ": "Czechia", "DE": "Germany",
    "DG": "Diego Garcia", "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica",
    "DO": "Dominican Republic", "DZ": "Algeria", "EA": "Ceuta & Melilla", "EC": "Ecuador",
    "EE": "Estonia", "EG": "Egypt", "EH": "Western Sahara", "ER": "Eritrea",
    "ES": "Spain", "ET": "Ethiopia", "FI": "Finland", "FJ": "Fiji",
    "FK": "Falkland Islands", "FM": "Micronesia", "FO": "Faroe Islands", "FR": "France",
    "GA": "Gabon", "GB": "United Kingdom", "GD": "Grenada", "GE": "Georgia",
    "GF": "French Guiana", "GG": "Guernsey", "GH": "Ghana", "GI": "Gibraltar",
    "GL": "Greenland", "GM": "Gambia", "GN": "Guinea", "GP": "Guadeloupe",
    "GQ": "Equatorial Guinea", "GR": "Greece", "GS": "South Georgia & South Sandwich Islands", "GT": "Guatemala",
    "GU": "Guam", "GW": "Guinea-Bissau", "GY": "Guyana", "HK": "Hong Kong",
    "HM": "Heard & McDonald Islands", "HN": "Honduras", "HR": "Croatia", "HT": "Haiti",
    "HU": "Hungary", "IC": "Canary Islands", "ID": "Indonesia", "IE": "Ireland",
    "IL": "Israel", "IM": "Isle of Man", "IN": "India", "IO": "British Indian Ocean Territory",
    "IQ": "Iraq", "IR": "Iran", "IS": "Iceland", "IT": "Italy",
    "JE": "Jersey", "JM": "Jamaica", "JO": "Jordan", "JP": "Japan",
    "KE": "Kenya", "KG": "Kyrgyzstan", "KH": "Cambodia", "KI": "Kiribati",
    "KM": "Comoros", "KN": "St. Kitts & Nevis", "KP": "North Korea", "KR": "South Korea",
    "KW": "Kuwait", "KY": "Cayman Islands", "KZ": "Kazakhstan", "LA": "Laos",
    "LB": "Lebanon", "LC": "St. Lucia", "LI": "Liechtenstein", "LK": "Sri Lanka",
    "LR": "Liberia", "LS": "Lesotho", "LT": "Lithuania", "LU": "Luxembourg",
    "LV": "Latvia", "LY": "Libya", "MA": "Morocco", "MC": "Monaco",
    "MD": "Moldova", "ME": "Montenegro", "MF": "St. Martin", "MG": "Madagascar",
    "MH": "Marshall Islands", "MK": "North Macedonia", "ML": "Mali", "MM": "Myanmar",
    "MN": "Mongolia", "MO": "Macau", "MP": "Northern Mariana Islands", "MQ": "Martinique",
    "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta", "MU": "Mauritius",
    "MV": "Maldives", "MW": "Malawi", "MX": "Mexico", "MY": "Malaysia",
    "MZ": "Mozambique", "NA": "Namibia", "NC": "New Caledonia", "NE": "Niger",
    "NF": "Norfolk Island", "NG": "Nigeria", "NI": "Nicaragua", "NL": "Netherlands",
    "NO": "Norway", "NP": "Nepal", "NR": "Nauru", "NU": "Niue",
    "NZ": "New Zealand", "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "French Polynesia", "PG": "Papua New Guinea", "PH": "Philippines", "PK": "Pakistan",
    "PL": "Poland", "PM": "St. Pierre & Miquelon", "PN": "Pitcairn Islands", "PR": "Puerto Rico",
    "PS": "Palestine", "PT": "Portugal", "PW": "Palau", "PY": "Paraguay",
    "QA": "Qatar", "RE": "Réunion", "RO": "Romania", "RS": "Serbia",
    "RU": "Russia", "RW": "Rwanda", "SA": "Saudi Arabia", "SB": "Solomon Islands",
    "SC": "Seychelles", "SD": "Sudan", "SE": "Sweden", "SG": "Singapore",
    "SH": "St. Helena", "SI": "Slovenia", "SJ": "Svalbard & Jan Mayen", "SK": "Slovakia",
    "SL": "Sierra Leone", "SM": "San Marino", "SN": "Senegal", "SO": "Somalia",
    "SR": "Suriname", "SS": "South Sudan", "ST": "São Tomé & Príncipe", "SV": "El Salvador",
    "SX": "Sint Maarten", "SY": "Syria", "SZ": "Eswatini", "TA": "Tristan da Cunha",
    "TC": "Turks & Caicos Islands", "TD": "Chad", "TF": "French Southern Territories", "TG": "Togo",
    "TH": "Thailand", "TJ": "Tajikistan", "TK": "Tokelau", "TL": "Timor-Leste",
    "TM": "Turkmenistan", "TN": "Tunisia", "TO": "Tonga", "TR": "Türkiye",
    "TT": "Trinidad & Tobago", "TV": "Tuvalu", "TW": "Taiwan", "TZ": "Tanzania",
    "UA": "Ukraine", "UG": "Uganda", "UM": "U.S. Outlying Islands", "US": "United States",
    "UY": "Uruguay", "UZ": "Uzbekistan", "VA": "Vatican City", "VC": "St. Vincent & Grenadines",
    "VE": "Venezuela", "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands", "VN": "Vietnam",
    "VU": "Vanuatu", "WF": "Wallis & Futuna", "WS": "Samoa", "XK": "Kosovo",
    "YE": "Yemen", "YT": "Mayotte", "ZA": "South Africa", "ZM": "Zambia",
    "ZW": "Zimbabwe",
}


def _flag_char(iso2):
    try:
        return "".join(chr(0x1F1E6 + ord(c) - 65) for c in iso2.upper())
    except Exception:
        return "🌍"


def _country_info(country, first_number):
    """রিটার্ন: (পূর্ণ নাম, ফ্ল্যাগ html)। premium_flags এ থাকলে প্রিমিয়াম ফ্ল্যাগ ও নাম ব্যবহার হয়।"""
    from text_utils import get_flag_and_code
    iso2 = str(country).strip().upper() if len(str(country).strip()) == 2 else ""
    if not iso2 and first_number:
        try:
            iso2 = get_flag_and_code(first_number)[1] or ""
        except Exception:
            iso2 = ""
    name, flag = None, None
    for _code, data in S.bot_settings.get("premium_flags", {}).items():
        if iso2 and data.get("iso") == iso2:
            name = data.get("name")
            if data.get("id"):
                flag = f'<tg-emoji emoji-id="{data["id"]}">{data.get("char", "🏳")}</tg-emoji>'
            else:
                flag = data.get("char")
            break
    if not name:
        name = ISO_NAMES.get(iso2) or (str(country) if len(str(country)) > 2 else iso2 or str(country))
    if not flag:
        flag = _flag_char(iso2) if iso2 else "🌍"
    return str(name).upper(), flag


def _icons():
    """অ্যাডমিন /seticons দিয়ে প্রিমিয়াম ইমোজি সেট করলে সেগুলো, নইলে ডিফল্ট।"""
    ids = S.bot_settings.get("stock_icons") or []

    def mk(i, char, default):
        if len(ids) > i and ids[i]:
            return f'<tg-emoji emoji-id="{ids[i]}">{char}</tg-emoji>'
        return default
    return (mk(0, "🔔", ICON_BELL), mk(1, "🌐", ICON_COUNTRY),
            mk(2, "🤖", ICON_SERVICE), mk(3, "📈", ICON_QUANTITY))


def _stock_html(cname, sname, qty, flag_html, app_html):
    c = _html.escape(cname)
    s = _html.escape(sname)
    bell, ic_c, ic_s, ic_q = _icons()
    return (
        f"<h3>{bell} NEW STOCK ADDED</h3>"
        f"<table bordered>"
        f"<tr><th>{ic_c} COUNTRY</th><td>{flag_html} {c}</td></tr>"
        f"<tr><th>{ic_s} SERVICE</th><td>{app_html} {s}</td></tr>"
        f"<tr><th>{ic_q} QUANTITY</th><td>{qty}</td></tr>"
        f"</table>"
    )


def _stock_html_inbtn(cname, sname, qty, flag_html, app_html, url, btn_icon_html):
    """টেবিলের নিচে সাদা বক্সের ভেতরেই NUMBER BOT বাটন (tg-button)।"""
    base = _stock_html(cname, sname, qty, flag_html, app_html)
    u = _html.escape(url, quote=True)
    return (base +
            f'<tg-button-row align="center"><tg-button type="url" url="{u}" style="primary">'
            f'{btn_icon_html} NUMBER BOT</tg-button></tg-button-row>')


def _stock_fallback(cname, sname, qty, flag_html, app_html):
    c = _html.escape(cname)
    s = _html.escape(sname)
    bell, ic_c, ic_s, ic_q = _icons()
    return render_body_text(
        f"{bell} <b>NEW STOCK ADDED</b>\n\n"
        f"<blockquote>{ic_c} <b>COUNTRY</b>   {flag_html} {c}\n"
        f"{ic_s} <b>SERVICE</b>   {app_html} {s}\n"
        f"{ic_q} <b>QUANTITY</b>   {qty}</blockquote>"
    )


# ---------------------------------------------------------------------
# অ্যাডমিন কমান্ড: /emojiid  এবং  /seticons
# ---------------------------------------------------------------------
def _custom_ids(msg):
    ents = [e for e in (msg.get("entities") or []) if e.get("type") == "custom_emoji"]
    ents.sort(key=lambda e: e.get("offset", 0))
    return [e["custom_emoji_id"] for e in ents if e.get("custom_emoji_id")]


def _emoji_kinds(ids):
    """getCustomEmojiStickers দিয়ে প্রতিটি আইডি অ্যানিমেটেড/ভিডিও/স্থির কি না জানায়।"""
    out = {}
    try:
        for i in range(0, len(ids), 200):
            chunk = ids[i:i + 200]
            r = requests.post(f"https://api.telegram.org/bot{cfg.TOKEN}/getCustomEmojiStickers",
                              json={"custom_emoji_ids": chunk}, timeout=15).json()
            for st in r.get("result", []) or []:
                kind = "animated" if st.get("is_animated") else ("video" if st.get("is_video") else "static")
                out[str(st.get("custom_emoji_id"))] = (kind, st.get("emoji", ""))
    except Exception:
        pass
    return out


def handle_emoji_cmd(chat_id, msg):
    """/emojiid <প্রিমিয়াম ইমোজি> -> আইডি + অ্যানিমেটেড কি না | /seticons <৪টি ইমোজি> | /animemojis"""
    from telegram_api import send_message
    text = msg.get("text", "")
    ids = _custom_ids(msg)

    if text.startswith("/animemojis"):
        import emojis as _E
        pool = {}
        for ch, i in getattr(_E, "GLOBAL_BODY_EMOJIS", {}).items():
            pool[str(i)] = ch
        for i in getattr(_E, "PEM", {}).values():
            for found in re.findall(r'emoji-id="(\d+)"', str(i)):
                pool.setdefault(found, "")
        kinds = _emoji_kinds(list(pool.keys()))
        if not kinds:
            send_message(chat_id, "Could not check emoji types right now. Try again later.")
            return
        anim = [f"{ch or kinds[i][1]} <code>{i}</code>" for i, ch in pool.items()
                if i in kinds and kinds[i][0] in ("animated", "video")]
        stat = sum(1 for i in pool if i in kinds and kinds[i][0] == "static")
        send_message(chat_id, f"🎞 Animated/video emojis in your bot: {len(anim)}  |  Static: {stat}\n\n" +
                     ("\n".join(anim[:60]) if anim else "None of them are animated."))
        return

    if text.startswith("/emojiid"):
        if not ids:
            send_message(chat_id, "Send: /emojiid followed by premium emoji(s)")
            return
        kinds = _emoji_kinds(ids)
        lines = []
        for i in ids:
            k = kinds.get(i, ("?", ""))[0]
            lines.append(f"<code>{i}</code>  —  {'🎞 animated' if k in ('animated', 'video') else k}")
        send_message(chat_id, "\n".join(lines))
        return

    # /seticons
    if len(ids) < 4:
        send_message(chat_id, render_body_text(
            "Usage: /seticons then 4 PREMIUM emojis in this order:\n"
            "1) bell  2) country  3) service  4) quantity\n"
            "Example: /seticons 🔔 🌐 🤖 📈 (pick them from the premium emoji keyboard)\n"
            "Tip: choose emojis that MOVE in the keyboard = animated. Check with /emojiid."))
        return
    S.bot_settings["stock_icons"] = ids[:4]
    try:
        from database import save_db
        save_db()
    except Exception:
        pass
    bell, ic_c, ic_s, ic_q = _icons()
    kinds = _emoji_kinds(ids[:4])
    moving = sum(1 for i in ids[:4] if kinds.get(i, ("", ""))[0] in ("animated", "video"))
    send_message(chat_id, render_body_text(f"✅ Stock card icons saved! ({moving}/4 animated)\n{bell} {ic_c} {ic_s} {ic_q}"))


def _accepts_parse_mode():
    import inspect
    from telegram_api import send_message
    return "parse_mode" in inspect.signature(send_message).parameters


# ---------------------------------------------------------------------
# ডিপ লিংক: NUMBER BOT বাটনে ক্লিক করলে ওই দেশ+সার্ভিসের নম্বর সরাসরি আসবে
# ---------------------------------------------------------------------
def _encode_payload(service, country):
    raw = f"{service}|{country}".encode("utf-8")
    tok = "stk_" + base64.urlsafe_b64encode(raw).decode().rstrip("=")
    return tok if len(tok) <= 64 else None   # Telegram এর সীমা ৬৪ অক্ষর


def _decode_payload(tok):
    try:
        body = tok[4:]
        body += "=" * (-len(body) % 4)
        service, country = base64.urlsafe_b64decode(body.encode()).decode("utf-8").split("|", 1)
        return service, country
    except Exception:
        return None, None


def handle_stock_deeplink(chat_id, msg, tok, user_callback):
    """/start stk_... -> ওই দেশ+সার্ভিসের নম্বর দেয়। সফলভাবে হ্যান্ডেল হলে True।"""
    from telegram_api import send_message, _answered
    service, country = _decode_payload(tok)
    if not service:
        return False
    res = send_message(chat_id, render_body_text("⌛ Getting your number..."))
    try:
        mid = res["result"]["message_id"]
    except Exception:
        return False
    fake_id = "deeplink_" + uuid.uuid4().hex[:10]
    _answered.add(fake_id)   # নকল callback এ answerCallbackQuery যাবে না
    call = {"id": fake_id, "from": msg.get("from", {}),
            "message": {"chat": msg["chat"], "message_id": mid},
            "data": f"g_c_{service}_{country}"}
    user_callback(call)
    return True


# ---------------------------------------------------------------------
# GIF সেট করা: অ্যাডমিন একটি GIF পাঠিয়ে ক্যাপশনে /setgif লিখবে (/setgif off = বন্ধ)
# ---------------------------------------------------------------------
def handle_setgif(chat_id, msg):
    from telegram_api import send_message
    cap = (msg.get("caption") or msg.get("text") or "").strip()
    if cap.lower().startswith("/setgif off"):
        S.bot_settings["stock_gif"] = ""
        ok = "🗑 Stock GIF removed."
    else:
        anim = msg.get("animation") or msg.get("video") or msg.get("document")
        if not anim or not anim.get("file_id"):
            send_message(chat_id, render_body_text(
                "Send a GIF/animation with the caption <code>/setgif</code> (use <code>/setgif off</code> to remove)."))
            return
        S.bot_settings["stock_gif"] = anim["file_id"]
        ok = "✅ Stock GIF saved! It will be sent with every NEW STOCK card."
    try:
        from database import save_db
        save_db()
    except Exception:
        pass
    send_message(chat_id, render_body_text(ok))


# 🎉 মেসেজ ইফেক্ট (শুধু প্রাইভেট চ্যাটে চলে)। বন্ধ করতে Render এ STOCK_EFFECT_ID=0 দিন।
DEFAULT_EFFECT_ID = "5046509860389126442"


def broadcast_new_stock(user_ids, country, service, qty, flag_html, app_html,
                        first_number=None, raw_service=None):
    """ব্যাকগ্রাউন্ড থ্রেডে সবাইকে পাঠায়।
    ধাপ ০: Rich মেসেজ + বাটন সাদা বক্সের ভেতরে  ->  ধাপ ১: Rich + বাটন নিচে (reply_markup)
    ->  ধাপ ২: সাধারণ মেসেজ। কোনো ধাপ না চললে নিজে থেকে পরের ধাপে নামে।"""
    cname, flag_html = _country_info(country, first_number)
    sname = str(service).upper()
    icon = _emoji_id(flag_html) or DEFAULT_BTN_ICON_ID

    tok = _encode_payload(raw_service or service, country)
    url = f"{_bot_url()}?start={tok}" if tok else _bot_url()
    btn = {"text": "NUMBER BOT", "url": url, "style": "primary", "icon_custom_emoji_id": icon}
    kb = {"inline_keyboard": [[btn]]}
    btn_icon_html = flag_html if "tg-emoji" in flag_html else f'<tg-emoji emoji-id="{icon}">🌐</tg-emoji>'
    html0 = _stock_html_inbtn(cname, sname, qty, flag_html, app_html, url, btn_icon_html)
    html1 = _stock_html(cname, sname, qty, flag_html, app_html)
    fb_text = _stock_fallback(cname, sname, qty, flag_html, app_html)
    effect = os.environ.get("STOCK_EFFECT_ID", DEFAULT_EFFECT_ID)
    gif = S.bot_settings.get("stock_gif") or ""

    def run():
        sess = requests.Session()
        base = f"https://api.telegram.org/bot{cfg.TOKEN}"
        st = {"mode": 0, "streak": 0, "effect": effect not in ("", "0")}

        def post(method, payload):
            return sess.post(f"{base}/{method}", json=payload, timeout=8).json()

        def with_effect(method, payload):
            """ইফেক্টসহ পাঠায়; ইফেক্ট নিয়ে সমস্যা হলে ইফেক্ট ছাড়া আবার।"""
            if st["effect"]:
                r = post(method, dict(payload, message_effect_id=effect))
                if r.get("ok") or "effect" not in str(r.get("description", "")).lower():
                    return r
                st["effect"] = False
            return post(method, payload)

        def attempt(uid):
            """রিটার্ন: 'ok' | 'user' (ইউজার ব্লক) | 'fail'"""
            mode = st["mode"]
            try:
                if mode == 0:
                    r = with_effect("sendRichMessage", {"chat_id": uid, "rich_message": {"html": html0}})
                elif mode == 1:
                    r = with_effect("sendRichMessage", {"chat_id": uid, "rich_message": {"html": html1}, "reply_markup": kb})
                else:
                    r = with_effect("sendMessage", {"chat_id": uid, "text": fb_text, "parse_mode": "HTML",
                                                    "disable_web_page_preview": True, "reply_markup": kb})
            except Exception:
                return "fail"
            if r.get("ok"):
                return "ok"
            desc = str(r.get("description", "")).lower()
            if any(k in desc for k in ("blocked", "deactivated", "chat not found", "forbidden")):
                return "user"
            if mode < 2:
                print(f"⚠️ stock card mode {mode} failed: {r}")
            return "fail"

        for uid in list(user_ids):
            if gif:
                try:
                    post("sendAnimation", {"chat_id": uid, "animation": gif})
                except Exception:
                    pass
            for _try in range(3):
                res = attempt(uid)
                if res in ("ok", "user"):
                    st["streak"] = 0
                    break
                st["streak"] += 1
                if st["mode"] < 2 and st["streak"] >= 2:
                    st["mode"] += 1          # এই ধাপ চলছে না, নিচের ধাপে নামি
                    st["streak"] = 0
                elif st["mode"] == 2:
                    break
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
