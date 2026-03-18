# 📍 CommuniFind: Hyper-Local Feature Locator

> A privacy-first, offline desktop application for discovering hyper-local community resources in Mumbai.

**Mini Project | Information Technology | Pillai College of Arts, Commerce & Science**
**Academic Year: 2025–26 | Guide: Ms. Satvika Guntha**

---

## 🧩 Problem It Solves

Major mapping platforms like Google Maps fail to locate non-commercial, hyper-local amenities in dense Indian cities — such as a park with a cricket pitch, a women-only public toilet, or a Dabbawala drop-off point. CommuniFind bridges this **"granularity gap"** using a locally curated, tag-based search system that works completely offline.

---

## ✨ Features

- 🔍 **Tag-Based Search** — Search using descriptive keywords like `park, cricket, shade`
- 📏 **Distance & Bearing Calculation** — Uses the Haversine formula via `geopy` to compute exact distance (KM) and direction (N/S/E/W)
- 🗺️ **Scatter Plot Visualization** — Custom `Matplotlib` map placing you at the center (0,0) with results plotted around you
- 🔒 **Fully Offline & Private** — No GPS tracking, no internet required, all data stays local
- 👥 **Crowdsourcing** — Users can submit missing places for admin review
- ⭐ **Favorites** — Save and quickly access frequently used locations
- 🛡️ **Admin Panel** — Moderate user-submitted locations and manage the database

---

## 🛠️ Tech Stack

| Component | Tool | Purpose |
|-----------|------|---------|
| Language | Python 3 | Core logic |
| GUI | CustomTkinter | Modern desktop UI |
| Geospatial | geopy | Distance & bearing calculation |
| Data Filtering | Pandas | Tag-based filtering |
| Visualization | Matplotlib | Scatter plot map |
| Database | MongoDB | Local offline data storage |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.x
- MongoDB running locally on `localhost:27017`

### Installation

```bash
# Clone the repo
git clone https://github.com/your-username/communifind.git
cd communifind

# Install dependencies
pip install customtkinter geopy pandas matplotlib pymongo pillow
```

### Run the App

```bash
python main.py
```

---

## 📁 Project Structure

```
communifind/
│
├── main.py                  # Main application & UI
├── backend.py               # Search logic, geospatial calculations
├── database_setup.py        # MongoDB setup & data ingestion
├── import.py                # Script to populate MongoDB with initial data
├── assets/                  # Images, icons, and UI resources
│   └── ...
├── CommuniFind.pdf          # Full project report (college submission)
├── requirements.txt         # Python dependencies
└── README.md
```

---

## ⚙️ First-Time Database Setup

Before running the app for the first time, populate the MongoDB database with the initial location data:

```bash
python import.py
```

> This reads from the `assets/` folder and loads all location records into your local MongoDB. You only need to run this **once**.

After that, launch the app normally:

```bash
python main.py
```

---

## 📸 Screenshots

| Landing Page | Search Results | Admin Panel |
|---|---|---|
| Login & Register | Distance + Bearing Map | Moderate submissions |

*(See `CommuniFind.pdf` for full screenshots)*

---

## 🔮 Future Scope

- 🌐 Vernacular language support (Marathi/Hindi tags)
- 📱 Mobile port using Kivy or Flutter
- 🛰️ Optional live GPS integration
- ☁️ Cloud sync for crowdsourced data

---

## 🎓 Academic Context

| Field | Details |
|-------|---------|
| Student | Pawani Rishi Devesh (Roll No. 5551) |
| College | Pillai College of Arts, Commerce & Science (Autonomous) |
| Department | Information Technology |
| Class | SYIT - A |
| Guide | Ms. Satvika Guntha |
| Year | 2025–26 |
