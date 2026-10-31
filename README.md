# 🚗 Car Number Plate Detection & Vehicle Tracking System

A real-time AI-powered vehicle tracking system that detects license plates from images using deep learning and logs vehicle entry data into Google Sheets via a web interface.

---

## 📌 Features

- 🔍 License Plate Detection using YOLOv8
- 🧠 Optical Character Recognition (OCR) using EasyOCR
- 🌐 Web Interface built with Streamlit
- 📷 Supports Image Upload & Camera Input (Mobile Compatible)
- ☁️ Automatic Data Logging to Google Sheets
- ⏱️ Stores Plate Number with Timestamp
- 🚫 Ignores irrelevant text like "IND"

---

## 🧠 Tech Stack

- Python
- YOLOv8 (Ultralytics)
- EasyOCR
- OpenCV
- Streamlit
- Google Sheets API (gspread)

---

## 🏗️ Project Structure

project/
│
├── models/
│ └── best.pt # Trained YOLO model
│
├── src/
│ ├── app.py # Streamlit web app
│ ├── detect.py # Detection logic
│ ├── sheets.py # Google Sheets integration
│ ├── credentials.json # (NOT INCLUDED in repo)
│
├── data/ # Dataset (ignored)
├── test_images/ # Sample test images
├── requirements.txt
└── README.md


---

## 🚀 How It Works

1. User uploads image or captures via camera  
2. YOLO model detects license plate region  
3. OCR extracts plate number  
4. Text is cleaned and validated  
5. Plate + timestamp is stored in Google Sheets  

---

## 📊 Sample Output

Detected Plate: MH12DE1433
Saved to Google Sheets with timestamp


---

## Google Sheets setup

Confirmed plates are logged to a Google Sheet through a service account.
The app only asks for access to Sheets, not the rest of your Drive.

1. In [Google Cloud Console](https://console.cloud.google.com/) create a project (or use one)
   and enable the **Google Sheets API**.
2. Go to *IAM & Admin → Service Accounts*, create a service account, then
   *Keys → Add key → JSON*. Save the file as `src/credentials.json`
   (it's git-ignored, never commit it).
3. Create a Google Sheet and **share it with the service account's email**
   (the `client_email` in the JSON) as **Editor**.
4. Copy the sheet ID from its URL, `https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit`,
   into `config.toml`:

   ```toml
   [sheets]
   spreadsheet_id = "<SHEET_ID>"
   worksheet = ""   # empty = first tab
   ```

Instead of the file you can also use environment variables, which is handier on a server:

| Variable | Value |
|---|---|
| `GOOGLE_CREDENTIALS` | The whole JSON key as a string |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the JSON key |
| `VDS_SHEETS_SPREADSHEET_ID` | The sheet ID |

If the sheet is empty a header row is added on first connect:
`Plate | Timestamp (IST) | Source | Detection Conf | OCR Conf | Format`.

If Sheets isn't set up the app still runs and detection still works;
`GET /api/health` tells you what's missing.

## Running the API

```bash
pip install -r requirements.txt
uvicorn src.api.main:app --reload
```

Docs are at http://localhost:8000/docs.

| Endpoint | What it does |
|---|---|
| `GET /api/health` | Model and Google Sheets status |
| `POST /api/detect` | Upload one or more images (`files`), returns boxes, plate text, confidences and a cropped plate per detection |
| `POST /api/logs` | Save a confirmed plate: `{"plate": "MH12DE1433", "source": "upload"}`. The same plate is refused within `dedupe_minutes` |
| `GET /api/logs` | Recent logs, newest first. Filters: `q`, `format`, `source`, `limit` |

Errors always look like `{"error": {"code": "...", "message": "..."}}`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Google Sheets and the model are mocked in the API tests, so no credentials are needed.

---

##Author :-
Mohnish Shandilya
