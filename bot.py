import requests
import re
import time
import os

BASE_URL = "https://www.ivasms.com"

EMAIL = os.getenv("IVASMS_EMAIL")
PASSWORD = os.getenv("IVASMS_PASSWORD")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


def send_telegram(text):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": text
    }

    requests.post(url, data=data)


class IvaSMS:

    def __init__(self, email, password):

        self.email = email
        self.password = password

        self.session = requests.Session()
        self.session.headers.update(headers)

    def login(self):

        login_url = BASE_URL + "/login"

        r = self.session.get(login_url)

        token = ""
        token_match = re.search(r'name="_token" value="(.*?)"', r.text)

        if token_match:
            token = token_match.group(1)

        payload = {
            "email": self.email,
            "password": self.password,
            "_token": token
        }

        r = self.session.post(login_url, data=payload)

        return "/portal" in r.url

    def get_sms(self):

        url = BASE_URL + "/portal/live/my_sms"

        r = self.session.get(url)

        html = r.text

        messages = re.findall(r"<tr.*?</tr>", html, re.S)

        results = []

        for row in messages:

            text = re.sub("<.*?>", " ", row)
            text = re.sub("\s+", " ", text)

            code_match = re.search(r"\b\d{4,8}\b", text)

            if code_match:

                code = code_match.group()

                results.append({
                    "code": code,
                    "message": text.strip()
                })

        return results


client = IvaSMS(EMAIL, PASSWORD)

if client.login():

    print("Login OK")

    seen = set()

    while True:

        try:

            sms_list = client.get_sms()

            print("Total Messages:", len(sms_list))

            for sms in sms_list:

                fingerprint = sms["code"] + sms["message"]

                if fingerprint not in seen:

                    message = f"""
🔐 OTP RECEIVED

Code: {sms['code']}

Message:
{sms['message']}
"""

                    print(message)

                    send_telegram(message)

                    seen.add(fingerprint)

            time.sleep(5)

        except Exception as e:

            print("Error:", e)

            time.sleep(5)

else:

    print("Login Failed")