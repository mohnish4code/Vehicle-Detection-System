# 🚗 License Plate Detection & Vehicle Tracking System

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

##Author :-
Mohnish Shandilya