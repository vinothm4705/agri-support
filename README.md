#  AgriSupport — Beginner Agriculture Support System for Tamilnadu

A smart, bilingual (English & Tamil) web application designed for beginner farmers in **Tamil Nadu, India**. It provides AI-powered crop guidance, real-time weather updates, market prices, pest & disease identification, and an intelligent chatbot — all in a clean, mobile-first Progressive Web App (PWA).

---

## Features

| Feature | Description |
|---------|-------------|
| **AI Chatbot** | Gemini AI-powered agricultural assistant with RAG (Retrieval-Augmented Generation) using local database context. Supports voice input via speech-to-text. |
| **Weather Dashboard** | Real-time weather data with 5-day forecast using OpenWeatherMap API. Includes AI-generated farming advisories based on current conditions. |
| **Crop Guide** | District-wise crop cultivation guides with step-by-step instructions for Tamil Nadu regions. |
| **Pest & Disease Info** | Crop-specific pest and disease database with symptoms, precautions, and solutions. |
| **AI Crop Diagnosis** | Upload a photo of a diseased crop and get AI-powered diagnosis using Gemini Vision. |
| **Market Prices** | Live crop market prices with price history tracking across Tamil Nadu districts. |
| **Farm Calculator** | Agricultural calculators for seed rate, fertilizer dosage, and other farming calculations. |
| **Sowing Calendar** | Month-wise sowing calendar with recommended crops and farming advice for Tamil Nadu. |
| **Agri News Ticker** | Live agriculture news from Google News RSS feed. |
| **Feedback System** | User feedback form with email notifications to admin. |
| **Admin Panel** | Protected admin dashboard to manage chatbot Q&A, crop prices, guides, and pest data. |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python, Flask |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript |
| **Database** | SQLite |
| **AI/ML** | Google Gemini API (google-genai SDK) |
| **Weather** | OpenWeatherMap API |
| **PWA** | Service Worker, Web App Manifest |
| **Styling** | Glassmorphism, CSS Gradients, Custom Animations |
| **Icons** | Font Awesome 6 (self-hosted) |
| **Fonts** | Google Fonts — Outfit (self-hosted) |

---

## Project Structure

```
agri_support_dev/
├── app.py                  # Main Flask application (all routes & logic)
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (API keys, secrets)
├── .gitignore              # Git ignore rules
│
├── templates/              # Jinja2 HTML templates
│   ├── index.html          # Home page
│   ├── language.html       # Language selection (EN/TA)
│   ├── chatbot.html        # AI Chatbot interface
│   ├── weather.html        # Weather dashboard
│   ├── guide.html          # Crop cultivation guide
│   ├── diagnose.html       # AI crop disease diagnosis
│   ├── pests.html          # Pest & disease information
│   ├── crop_prices.html    # Market prices
│   ├── calculator.html     # Farm calculator
│   ├── calendar.html       # Sowing calendar
│   ├── feedback.html       # User feedback form
│   ├── about.html          # About page
│   ├── login.html          # Admin login
│   ├── admin.html          # Admin dashboard
│   ├── admin_chatbot.html  # Admin: Manage Q&A
│   ├── admin_prices.html   # Admin: Manage prices
│   ├── admin_guide.html    # Admin: Manage guides
│   ├── admin_pests.html    # Admin: Manage pests
│   └── offline.html        # Offline fallback page
│
├── static/
│   ├── style.css           # Global stylesheet
│   ├── loader.js           # Leaf loader animation
│   ├── service-worker.js   # PWA service worker
│   ├── manifest.json       # PWA manifest
│   ├── images/             # App icons & crop/district images
│   ├── pests/              # Pest & disease images
│   └── vendor/             # Self-hosted fonts & Font Awesome
│
├── languages/
│   ├── en.json             # English translations
│   └── ta.json             # Tamil translations
│
└── data/
    └── farming_advisories.json  # Static fallback advisories (TNAU-sourced)
```

---

## Setup & Installation

### Prerequisites
- Python 3.9 or higher
- A [Google Gemini API Key](https://aistudio.google.com/apikey)
- An [OpenWeatherMap API Key](https://openweathermap.org/api)

### Steps

**1. Create a virtual environment**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Create a `.env` file**

Create a `.env` file in the project root with the following:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
OPENWEATHER_API_KEY=your_openweather_api_key_here
SECRET_KEY=your_flask_secret_key_here

# Email Configuration (Optional — for feedback notifications)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_app_password
ADMIN_EMAIL=your_email@gmail.com

# Admin Panel
ADMIN_PASSWORD=your_admin_password
```

**4. Run the application**
```bash
python app.py
```

**5. Open in browser**
```
http://localhost:5000
```

---

## Bilingual Support

The app fully supports **English** and **Tamil**.

- Language selection on first visit
- All UI labels, error messages, and static content are localized
- AI chatbot responds in the selected language
- Crop guides, pest info, and advisories available in both languages

---

## Progressive Web App (PWA)

AgriSupport is installable as a native-like app on mobile devices:

- Add to Home Screen support
- Splash screen with app icon
- Standalone display (no browser chrome)
- Network-first Service Worker with offline cache fallback
- Works on Android, iOS, and Desktop

---

## AI Features

### Chatbot (RAG Architecture)
1. User question is first matched against local SQLite Q&A database
2. If no strong match, the system augments the query with relevant context from the database (crop prices, pest data)
3. The augmented prompt is sent to **Gemini Flash Lite** for generation
4. Unanswered questions are logged for admin review

### Crop Disease Diagnosis
- Upload a photo of a diseased crop leaf
- Gemini Vision analyzes the image
- Returns disease name, cause, symptoms, and treatment recommendations

### Weather Advisories
- AI generates farming-specific advisories based on real-time weather
- Falls back to TNAU-sourced static advisories if AI quota is exhausted

---

## Admin Panel

Access the admin panel at `/login` to:

- View and manage unanswered chatbot questions
- Add/edit/delete chatbot Q&A entries
- Update crop market prices
- Manage crop cultivation guides
- Add pest & disease records

> **Note:** This project requires valid API keys for Google Gemini and OpenWeatherMap to function fully.
