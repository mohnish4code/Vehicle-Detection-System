import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import json
import os
import pytz

# Setup scope
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

if "GOOGLE_CREDENTIALS" in os.environ:
    # STREAMLIT CLOUD
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
else:
    # LOCALHOST
    creds = ServiceAccountCredentials.from_json_keyfile_name("src/credentials.json", scope)

client = gspread.authorize(creds)
sheet = client.open("Vehicle_Tracking_System").sheet1


def save_to_sheets(plate, image_name):
    ist = pytz.timezone('Asia/Kolkata')
    timestamp = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")

    sheet.append_row([
        plate,
        timestamp,
        image_name
    ])