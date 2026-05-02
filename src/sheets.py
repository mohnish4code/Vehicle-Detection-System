import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Setup scope
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# Load credentials
creds = ServiceAccountCredentials.from_json_keyfile_name("src/credentials.json", scope)
client = gspread.authorize(creds)

# Open your sheet (IMPORTANT: name must match exactly)
sheet = client.open("Vehicle_Tracking_System").sheet1


def save_to_sheets(plate, image_name):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sheet.append_row([
        plate,
        timestamp,
        image_name
    ])
