import json
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# Configuration (Token & Owner ID)
# ==========================================
TOKEN = "8883386833:AAHZXPssYenrKnn5gerOU4KFcpbYwZ64m30"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"
FILE_URL = f"https://api.telegram.org/file/bot{TOKEN}/"

OWNER_ID = 8253965718
BOT_USERNAME = ""
DB_FILE = "bot_data.json"

# Panel API Base URLs
STEX_BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tness/@public/api"
VOLTX_BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnevs/@public/api"
ZENEX_BASE_URL = "https://api.zenexnetwork.com"
MINT_BASE_URL = "https://api.2oo9.cloud/MXS47FLFX0U/tnemn/@public/api"

# ==========================================
# Firebase Setup
# ==========================================
firebase_credentials_json = r"""
{
  "type": "service_account",
  "project_id": "mustafizur-ec7c8",
  "private_key_id": "79617568deafd475e45c6fad549df9331a82e9fb",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQDNUm6F4bp/mo0x\nswQ4Qzd17t+OhCRlSqHkHyqYHYaPGgPRAemT/rljN2PRxwxFYstbeF2sOn9BMHEY\nRsRSUeUjpixzE793hRI6ru6HMPr/WILDcofSvGvVvCMPFhbv6maJC8ZztlFt161R\n0WG5pqyA//JL/uYDB3N2h+mtm0mEc3GXhNYjt8qJoEqgJuSqtoXhqTXeLPAy5M1p\nAp+hvGbCA3BcTT26wMjqqmxO4r8OzK/hxqj4gnQAW/FOQm9PJ7iK0xjrFTkIMx1m\nZZyY6mExErXBKKbEyWXlZuFQKu+8nsNLlxENnxFhIqhSQO/0xnMSMBFcNiLFC6aI\nk2jUj0kfAgMBAAECggEADoT+SNxyHlT1GCcjLMFgGihmycLBeiJBeYrUrcYkvljm\nHTEn7e3M+V2w4uRTE1MNs227HhNS7W66CK/0cSfWbuNw8EBcwVx5Mgot1wSZM1Z0\nhNLEFRx6+bXgus/illu6nYVmJselUYG3gXovkXveZg7zePlRFbTArwikd0DsfX+2\nAyR65IuguwqdTRHJOLpb+t7w+N75i9kQ3K8m5PZbhNwo2/i2f0YGU287egopKxMO\nf4DZefw9RhJQ0FNEoMoEcGpM9g6MhK6lcvuFChUZdZcp93A8u/ks7NPmawyDth6B\nWl2ATXLHg4a8WPo8mBTruM0DF0EZXt1ttmBwKfaKfQKBgQDmGKXoOHVXe6ABD7IW\nLYcDLFgSEaprxrpkYX4XHpdjvFt1NhaAll+q4Pgl6kdYyfhuPfhAF6HboX7s9xsG\ntn0azZzPV6gtob3soGqwRS7lq0dhl11+PiKwlsfVPfOv5R8MQLCLKnZ9XoiKeQ2v\nK/k/TOXCWt2O7/h/QMtxk0R63QKBgQDkb8qSf7XTfZ4qe5liuBei5jTzFuP9NcAJ\nwgADYfXW9TaJtgWNHQ8jiUruBmQmbbFXkOVOkRMDWWPNwfOuTaxJzxF6af86Oqwz\nQH/hKdOlk2dRQfLriB632Q6dNibbYmHxfc2oHCjULgFV5zLHkyotrqhNRzYhNzdN\nZ8Fq+9/eKwKBgQCXu29EaF6w1twXdxM33sPmisp09+NK+RyW71dnxYuNgHtLGuTR\n3NevZnUdA5YS7fT+Na1MDol0vNVnTDgtQA/VqfsbG7HSjZMhxFM2dBjN6RnEOD21\n7yGPE48phpX4yv2jZdFFpDXIzJr7vYIRnszZOktU0/jAtmxG9iJyfeutnQKBgFSN\n1It5XhIUUzEiYtoZjhYr47l+5ZDaDmUOO/cEkXypczByAYgEE5BxxxxnnTZkL9pb\ntaTpKgJ5WenVOp9v/K+tR6jqByDEiuzFmQ/87WxCLWH0aTgpQEWIwFIMs0FNHzfF\n+xOYqLww8yma1D7vCBO0rHM+Qpj02TF7kCpLZMfVAoGBAKSfoWJcjZIaHDjPd8xI\niKwZkgbEL1mL6CTkd+JULcF60h/s7GlFYQjfNJoDadStSC0NC6WBKKh0fc4BF0tB\nqN1guydeDsW5evqGfIS0koUH/IWbzp52nVM6NdZT4naGvHJUHb038d1DuE0+Th8A\nLCPTWyxO0SUibUfhm6eSrpzG\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-fbsvc@mustafizur-ec7c8.iam.gserviceaccount.com",
  "client_id": "115218883380702345302",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-fbsvc%40mustafizur-ec7c8.iam.gserviceaccount.com",
  "universe_domain": "googleapis.com"
}
"""

try:
    cred_dict = json.loads(firebase_credentials_json)
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("✅ Firebase Connected! (Full Sync Enabled)")
except Exception as e:
    print(f"❌ Firebase Error: {e}")
    db = None