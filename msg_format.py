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
    uname = (getattr(cfg, "MUSTAFIZUR_OTP_3BOT", "") or FALLBACK_BOT).lstrip("@")
    return f"https://t.me/{uname}"


def _emoji_id(emoji_html):
    m = re.search(r'emoji-id="(\d+)"', emoji_html or "")
    return m.group(1) if m else None


# =====================================================================
# 1) NEW STOCK ADDED  (সবার কাছে ব্রডকাস্ট)
# =====================================================================
# বাঁদিকের আইকন বদলাতে চাইলে এখানে প্রিমিয়াম ইমোজি বসান, যেমন:
#   ICON_SERVICE = '<tg-emoji emoji-id="আইডি">🤖</tg-emoji>'
ICON_BELL = "🔔"
ICON_COUNTRY = PEM["world"]
ICON_SERVICE = "🤖"
ICON_QUANTITY = "📈"
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


def _stock_html(cname, sname, qty, flag_html, app_html):
    c = _html.escape(cname)
    s = _html.escape(sname)
    return (
        f"<h3>{ICON_BELL} NEW STOCK ADDED</h3>"
        f"<table bordered>"
        f"<tr><th>{ICON_COUNTRY} COUNTRY</th><td>{flag_html} {c}</td></tr>"
        f"<tr><th>{ICON_SERVICE} SERVICE</th><td>{app_html} {s}</td></tr>"
        f"<tr><th>{ICON_QUANTITY} QUANTITY</th><td>{qty}</td></tr>"
        f"</table>"
    )


def _stock_fallback(cname, sname, qty, flag_html, app_html):
    c = _html.escape(cname)
    s = _html.escape(sname)
    return render_body_text(
        f"{ICON_BELL} <b>NEW STOCK ADDED</b>\n\n"
        f"<blockquote>{ICON_COUNTRY} <b>COUNTRY</b>   {flag_html} {c}\n"
        f"{ICON_SERVICE} <b>SERVICE</b>   {app_html} {s}\n"
        f"{ICON_QUANTITY} <b>QUANTITY</b>   {qty}</blockquote>"
    )


def broadcast_new_stock(user_ids, country, service, qty, flag_html, app_html, first_number=None):
    """ব্যাকগ্রাউন্ড থ্রেডে সবাইকে পাঠায়। flag_html এখন আর লাগে না, দেশ নিজেই বের করা হয়।"""
    cname, flag_html = _country_info(country, first_number)
    sname = str(service).upper()
    icon = _emoji_id(flag_html) or DEFAULT_BTN_ICON_ID
    btn = {"text": "NUMBER BOT", "url": _bot_url(), "style": "primary", "icon_custom_emoji_id": icon}
    kb = {"inline_keyboard": [[btn]]}
    rich_html = _stock_html(cname, sname, qty, flag_html, app_html)
    fb_text = _stock_fallback(cname, sname, qty, flag_html, app_html)

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
