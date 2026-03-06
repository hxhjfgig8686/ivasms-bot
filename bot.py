import os
import re
import time
from html import unescape
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener

BASE_URL = os.getenv("IVASMS_BASE_URL", "https://www.ivasms.com").rstrip("/")
POLL_INTERVAL_SECONDS = int(os.getenv("IVASMS_POLL_INTERVAL", "5"))
RETRY_DELAY_SECONDS = int(os.getenv("IVASMS_RETRY_DELAY", "3"))

EMAIL = os.getenv("IVASMS_EMAIL", "")
PASSWORD = os.getenv("IVASMS_PASSWORD", "")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


class SimpleResponse:
    def __init__(self, text, url):
        self.text = text
        self.url = url


class SimpleSession:
    def __init__(self):
        cookie_jar = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(cookie_jar))

    def get(self, url, timeout=20):
        request = Request(url, method="GET")
        with self.opener.open(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="ignore")
            return SimpleResponse(html, response.geturl())

    def post(self, url, data=None, timeout=20):
        encoded = urlencode(data or {}).encode("utf-8")
        request = Request(url, data=encoded, method="POST")
        with self.opener.open(request, timeout=timeout) as response:
            html = response.read().decode("utf-8", errors="ignore")
            return SimpleResponse(html, response.geturl())


def send_telegram(text, bot_token=BOT_TOKEN, chat_id=CHAT_ID):
    if not bot_token or not chat_id:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    SimpleSession().post(url, data={"chat_id": chat_id, "text": text}, timeout=20)


def extract_code(text):
    match = re.search(r"\b\d{4,8}\b", text)
    return match.group() if match else None


def _clean_html_text(html_fragment):
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_message_text_from_row(row_html):
    cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", row_html, flags=re.IGNORECASE | re.DOTALL)
    cleaned_cells = []
    for cell in cells:
        cleaned = _clean_html_text(cell)
        if cleaned:
            cleaned_cells.append(cleaned)

    code_cells = [cell for cell in cleaned_cells if extract_code(cell)]
    if code_cells:
        # غالباً خلية الرسالة تحتوي نص أطول من باقي الأعمدة (رقم/تاريخ)
        return max(code_cells, key=len)

    return _clean_html_text(row_html)


def _extract_messages_with_codes(html_text):
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", html_text, flags=re.IGNORECASE | re.DOTALL)
    messages = []

    for row in rows:
        message_text = _extract_message_text_from_row(row)
        code = extract_code(message_text)
        if code:
            messages.append({"code": code, "message": message_text})

    return messages


def _extract_csrf_token(html_text):
    token_match = re.search(r'name="_token"\s+value="([^"]+)"', html_text)
    return token_match.group(1) if token_match else ""


class IvaSMS:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.session = SimpleSession()

    def login(self):
        login_url = BASE_URL + "/login"
        login_page = self.session.get(login_url, timeout=20)
        token = _extract_csrf_token(login_page.text)

        payload = {"email": self.email, "password": self.password, "_token": token}
        response = self.session.post(login_url, data=payload, timeout=20)
        return "/portal" in response.url

    def get_sms(self):
        url = BASE_URL + "/portal/live/my_sms"
        response = self.session.get(url, timeout=20)
        return _extract_messages_with_codes(response.text)


def run_polling_loop(email=EMAIL, password=PASSWORD):
    if not email or not password:
        print("Missing IVASMS_EMAIL or IVASMS_PASSWORD")
        return

    client = IvaSMS(email, password)

    try:
        logged_in = client.login()
    except Exception as error:  # noqa: BLE001
        print("Login Error:", error)
        return

    if not logged_in:
        print("Login Failed")
        return

    print("Login OK")
    seen_fingerprints = set()

    while True:
        try:
            messages = client.get_sms()
            print("Total Messages:", len(messages))

            for msg_data in messages:
                fingerprint = f"{msg_data['code']}|{msg_data['message']}"
                if fingerprint in seen_fingerprints:
                    continue

                telegram_message = (
                    "🔐 OTP RECEIVED\n\n"
                    f"🔑 Code: {msg_data['code']}\n\n"
                    f"📩 Full Message:\n{msg_data['message']}"
                )

                print(telegram_message)
                send_telegram(telegram_message)
                seen_fingerprints.add(fingerprint)

            time.sleep(POLL_INTERVAL_SECONDS)

        except Exception as error:  # noqa: BLE001
            print("Error:", error)
            time.sleep(RETRY_DELAY_SECONDS)


if __name__ == "__main__":
    run_polling_loop()
