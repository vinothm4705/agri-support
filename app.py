from flask import Flask, render_template, request, session, jsonify, redirect, url_for
import sqlite3
import json
import requests
import difflib
import feedparser
import re
import html
import urllib.parse
from datetime import datetime
from datetime import timedelta
from threading import Thread
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import threading
import os
import base64
import io

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
app.permanent_session_lifetime = timedelta(days=365)

OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
OPENWEATHER_BASE_URL = "https://api.openweathermap.org/data/2.5"

@app.template_filter('timestamp_to_datetime')
def timestamp_to_datetime(timestamp):
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

@app.context_processor
def inject_now():
    return {
        'current_year': datetime.now().year,
        't': load_language()
    }


def load_language():
    lang = session.get("lang", "en")
    with open(f"languages/{lang}.json", "r", encoding="utf-8") as f:
        return json.load(f)


def translate_category(category, lang="en"):
    if not category:
        return category

    c = category.strip().lower()

    if lang == "ta":
        if c == "pest":
            return "பூச்சி"
        elif c == "disease":
            return "நோய்"
        else:
            return category
    else:
        if c == "pest":
            return "Pest"
        elif c == "disease":
            return "Disease"
        else:
            return category




def get_agri_news(lang="en"):
    news_items = []
    
    if lang == "ta":
        # Tamil Query: "Agriculture" (English Keyword) + Tamil Interface (hl=ta)
        # This is more robust than strict Tamil encoding that often returns 0 results
        rss_url = "https://news.google.com/rss/search?q=Agriculture&hl=ta&gl=IN&ceid=IN:ta"
    else:
        # English Query: "Agriculture India"
        rss_url = "https://news.google.com/rss/search?q=Agriculture+India&hl=en-IN&gl=IN&ceid=IN:en"
        
    try:
        feed = feedparser.parse(rss_url)
        
        # Get top 12 entries for the scrolling ticker
        for entry in feed.entries[:12]:
            title = entry.title
            source = entry.source.title if hasattr(entry, 'source') else "News"
            link = entry.link
            
            # Clean title
            if " - " in title:
                title = title.rsplit(" - ", 1)[0]
            
            # Parse Summary (remove HTML tags if any, keep it simple)
            summary = ""
            if hasattr(entry, 'summary'):
                import re
                import html
                clean = re.compile('<.*?>')
                summary = re.sub(clean, '', entry.summary)
                summary = html.unescape(summary) # Fix &nbsp; etc
                # Truncate if too long
                if len(summary) > 120:
                    summary = summary[:117] + "..."
            
            # Format Date
            date_str = ""
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                date_str = datetime(*entry.published_parsed[:6]).strftime("%d %b %H:%M")

            item = {
                "title": title,
                "link": link,
                "source": source,
                "date": date_str,
                "summary": summary
            }
            news_items.append(item)
            
    except Exception as e:
        print(f"News Fetch Error: {e}")
        # Return empty list on error, template handles empty state
        pass
        
    return news_items


def send_email_async(subject, body, to_email):
    """Send email in a separate thread to avoid blocking"""
    try:
        smtp_server = os.getenv("MAIL_SERVER", "smtp.gmail.com")
        smtp_port = int(os.getenv("MAIL_PORT", 587))
        sender_email = os.getenv("MAIL_USERNAME")
        password = os.getenv("MAIL_PASSWORD")

        if not sender_email or not password:
            print("Email credentials missing in .env")
            return

        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, password)
        server.send_message(msg)
        server.quit()
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")

def send_feedback_email(name, category, rating, message):
    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        return

    subject = f"AgriSupport Feedback: {category} ({rating} Stars)"
    body = f"""
    <h2>New Feedback Received</h2>
    <p><strong>Name:</strong> {name or 'Anonymous'}</p>
    <p><strong>Category:</strong> {category}</p>
    <p><strong>Rating:</strong> {rating}/5</p>
    <p><strong>Message:</strong></p>
    <blockquote style="background:#f9f9f9; padding:10px; border-left:4px solid #4CAF50;">
        {message}
    </blockquote>
    """
    
    # Run in background thread
    threading.Thread(target=send_email_async, args=(subject, body, admin_email)).start()
def get_crop_guide_from_db(district, crop):
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT crop_name_en, crop_name_ta,
               district_name_en, district_name_ta,
               season_en, season_ta,
               soil_en, soil_ta,
               explanation_en, explanation_ta
        FROM crop_guide
        WHERE district=? AND crop=?
        LIMIT 1
    """, (district, crop))

    guide_row = cursor.fetchone()

    # Fetch crop guide steps
    cursor.execute("""
        SELECT step_no, step_en, step_ta
        FROM crop_guide_steps
        WHERE district=? AND crop=?
        ORDER BY step_no
    """, (district, crop))

    steps = cursor.fetchall()
    conn.close()

    if not guide_row:
        return None

    return {
        "crop_name_en": guide_row[0],
        "crop_name_ta": guide_row[1],
        "district_name_en": guide_row[2],
        "district_name_ta": guide_row[3],
        "season_en": guide_row[4],
        "season_ta": guide_row[5],
        "soil_en": guide_row[6],
        "soil_ta": guide_row[7],
        "explanation_en": guide_row[8],
        "explanation_ta": guide_row[9],
        "steps": steps
    }


def get_pest_disease_from_db(crop, lang="en"):
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()

    if lang == "ta":
        cursor.execute("""
            SELECT name_ta, category, symptoms_ta, precautions_ta, solutions_ta, image
            FROM pest_disease
            WHERE crop = ?
        """, (crop,))
    else:
        cursor.execute("""
            SELECT name_en, category, symptoms_en, precautions_en, solutions_en, image
            FROM pest_disease
            WHERE crop = ?
        """, (crop,))

    rows = cursor.fetchall()
    conn.close()

    # Translate category in results
    translated_rows = []
    for r in rows:
        name = r[0]
        category = translate_category(r[1], lang)
        symptoms = r[2]
        precautions = r[3]
        solutions = r[4]
        image = r[5]

        translated_rows.append((name, category, symptoms, precautions, solutions, image))

    return translated_rows


from google import genai
from google.genai import types

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

def augment_context(question):
    context_parts = []
    
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()
    
    # 1. Search Crop Prices
    # Simple check if any district or crop name is in the question
    cursor.execute("SELECT district_en, crop_en, price, unit_en, updated_on FROM crop_prices")
    price_rows = cursor.fetchall()
    
    found_price = False
    match_limit = 5
    matches = 0
    
    for dist, crop, price, unit, date in price_rows:
        # Relaxed Matching: If crop matches OR district matches
        if (crop.lower() in question.lower()) or (dist.lower() in question.lower() and "price" in question.lower()):
             context_parts.append(f"- Market Price: {crop} in {dist} is ₹{price} per {unit} (Updated: {date})")
             matches += 1
             if matches >= match_limit:
                 break
            
    # 2. Search Pests
    cursor.execute("SELECT crop, name_en, symptoms_en, solutions_en FROM pest_disease")
    pest_rows = cursor.fetchall()
    
    for crop, name, symp, sol in pest_rows:
        if crop.lower() in question.lower() or name.lower() in question.lower():
            context_parts.append(f"- Pest Info ({crop} - {name}): Symptoms: {symp}. Solution: {sol}")

    conn.close()
    
    if context_parts:
        return "Context Data from Local Database:\n" + "\n".join(context_parts)
    return ""

def format_ai_response(text):
    """Convert markdown-style AI response to lightweight HTML for display."""
    if not text:
        return text
    
    # Remove markdown code fences if any
    text = re.sub(r'```[\s\S]*?```', lambda m: m.group(0).replace('```', ''), text)
    
    # Bold: **text** → <strong>text</strong>
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    
    # Italic: *text* → <em>text</em>
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'<em>\1</em>', text)
    
    # Bullet points: lines starting with - or * → <li>
    lines = text.split('\n')
    result = []
    in_list = False
    
    for line in lines:
        stripped = line.strip()
        if re.match(r'^[\-\*•]\s+', stripped):
            if not in_list:
                result.append('<ul style="margin: 8px 0; padding-left: 20px;">')
                in_list = True
            item = re.sub(r'^[\-\*•]\s+', '', stripped)
            result.append(f'<li style="margin: 4px 0;">{item}</li>')
        else:
            if in_list:
                result.append('</ul>')
                in_list = False
            if stripped:
                result.append(f'{stripped}<br>')
    
    if in_list:
        result.append('</ul>')
    
    # Clean trailing <br>
    output = '\n'.join(result)
    if output.endswith('<br>'):
        output = output[:-4]
    
    return output


def get_chatbot_answer(question, chat_history=None):
    lang = session.get("lang", "en")
    question = question.lower().strip()
    
    # 0. Basic Greetings Override
    greetings = ["hi", "hello", "vanakkam", "hey", "hai", "name","ஹாய்","வணக்கம்","ஹலோ","ஹாய் ஹலோ"]
    if question in greetings:
        if lang == "ta":
            return "வணக்கம்! நான் உங்கள் வேளாண் உதவியாளர். விவசாயம் தொடர்பான உங்கள் கேள்விகளைக் கேளுங்கள்."
        return "Hello! I am your Agriculture Assistant. Please ask me anything about farming, crops, or pests."

    # 1. RAG Triggers (Dynamic Data Priority)
    # If the user asks about dynamic topics (prices, pests), we prefer AI over static text.
    rag_keywords = [
        "price", "cost", "market", "rate", 
        "pest", "disease", "worm", "bug", "solution", "control", "medicine",
        "weather", "climate", "rain", "temperature", "forecast"
    ]
    force_ai = any(w in question for w in rag_keywords)

    # 2. Local DB Search (Static Q&A)
    # We only restrict this if we are not forced to use AI
    best_match_answer = None
    highest_score = 0
    
    if not force_ai:
        conn = sqlite3.connect("agri_support.db")
        cursor = conn.cursor()
        cursor.execute("SELECT keyword_en, keyword_ta, answer_en, answer_ta FROM chatbot_qa")
        rows = cursor.fetchall()
        conn.close()

        user_words = question.split()

        for keyword_en, keyword_ta, answer_en, answer_ta in rows:
            if lang == "en" and keyword_en:
                db_keywords = [k.strip().lower() for k in keyword_en.split(",") if k.strip()]
            elif lang == "ta" and keyword_ta:
                db_keywords = [k.strip() for k in keyword_ta.split(",") if k.strip()]
            else:
                continue

            row_score = 0
            for k in db_keywords:
                if k in question:
                    row_score += 1  # Count each matched keyword as 1
                elif len(k) > 3:
                    matches = difflib.get_close_matches(k, user_words, n=1, cutoff=0.7)
                    if matches:
                        row_score += 1  # Typo-tolerant match also counts as 1
            
            if row_score > highest_score:
                highest_score = row_score
                best_match_answer = answer_ta if lang == "ta" else answer_en

    # 3. DECISION: Use Local or AI?
    # If explicitly NOT dynamic topic AND strong match found (3 or 2 keywords) -> Use Local
    if not force_ai and highest_score >= 3 and best_match_answer:
        return best_match_answer

    # 4. AI GENERATION (Google GenAI SDK)
    try:
        # Fetch Context
        db_context = augment_context(question)
        
        # Build Prompt
        base_instruction = (
            "You are an expert Agriculture Assistant for a beginner farmer in Tamil Nadu. "
            "your answers must be suited for Tamil Nadu region climate and soil. "
            "Answer simply and clearly. Keep your answer short and crisp. "
            "Answer the user's question directly and completely. "
            "Use bullet points and bold text to structure your answer when appropriate. "
            "If context data is provided below, USE IT to form your answer. "
            f"Respond in {('Tamil' if lang == 'ta' else 'English')}."
        )
        
        # Build conversation memory (last 5 exchanges)
        conversation_context = ""
        if chat_history and len(chat_history) > 0:
            recent = chat_history[-10:]  # Last 5 pairs (user + bot)
            conv_lines = []
            for msg in recent:
                role = "User" if msg.get("type") == "user" else "Assistant"
                # Strip HTML tags from stored content for clean context
                content = re.sub(r'<[^>]+>', '', str(msg.get("content", "")))
                conv_lines.append(f"{role}: {content}")
            conversation_context = "Previous Conversation:\n" + "\n".join(conv_lines)
        
        prompt = f"{base_instruction}\n\n{conversation_context}\n\n{db_context}\n\nUser Question: {question}"

        # Configure Tools
        # Search Grounding tool disabled due to strict Free-Tier API Quota limitations
        # The AI will now rely purely on its massive internal knowledge base + local DB context
        
        response = client.models.generate_content(
            model="models/gemini-flash-lite-latest",
            contents=prompt
        )
        return response.text
        
    except Exception as e:
        print(f"AI Error: {e}")
        pass

    # 5. FALLBACK
    try:
        conn = sqlite3.connect("agri_support.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM unanswered_questions WHERE LOWER(question) = LOWER(?)", (question,))
        if not cursor.fetchone():
            cursor.execute("INSERT INTO unanswered_questions (question) VALUES (?)", (question,))
            conn.commit()
        conn.close()
    except Exception as e:
        print("Log Error:", e)

    return (
        "மன்னிக்கவும், இப்போது எனக்கு பதில் தெரியவில்லை, நான் உங்கள் கேள்வியை குறித்துக் கொண்டேன்." if lang == "ta" 
        else "Sorry, I don't know the answer right now. I have noted your question."
    )


def generate_advisories(weather_data, lang):
    advisories = []

    if not weather_data or 'main' not in weather_data:
        return advisories

    temp = weather_data['main']['temp']
    humidity = weather_data['main']['humidity']
    pressure = weather_data['main'].get('pressure', 1013)
    wind_speed = weather_data.get('wind', {}).get('speed', 0)
    rain_1h = weather_data.get('rain', {}).get('1h', 0)
    weather_desc = weather_data['weather'][0]['description']
    
    # 1. TRY GEMINI AI GENERATION
    ai_success = False
    try:
        # tailoring prompt for Tamil Nadu Beginner Farmers
        district_name = weather_data.get('name', 'Tamil Nadu')
        context = f"Region: {district_name} District, Tamil Nadu, India. Consider crops suitable for {district_name} soil and climate. Audience: Beginner Farmers."
        weather_context = f"Temperature: {temp}°C, Humidity: {humidity}%, Wind: {wind_speed} m/s, Condition: {weather_desc}."
        
        system_instruction = f"""
        You are an expert agricultural scientist helping beginner farmers. {context}
        Based on the current weather ({weather_context}), provide ONE specific, practical farming advisory.
        Always start your response by explicitly mentioning the {district_name} district (e.g. "For farmers in {district_name}:").
        Focus on immediate actions like irrigation, pest control, or harvest delay.
        Keep it short (max 2 sentences). Do not use asterisks or formatting.
        """
        
        if lang == 'ta':
            prompt = f"{system_instruction} Provide the response in proper Tamil language."
        else:
            prompt = f"{system_instruction} Provide the response in simple English."

        # Use the global 'client' initialized at module level
        response = client.models.generate_content(
            model="models/gemini-flash-lite-latest",
            contents=prompt
        )
        
        if response and response.text:
            cleaned_text = response.text.strip().replace('*', '').replace('"', '')
            advisories.append({'en': cleaned_text, 'ta': cleaned_text})
            ai_success = True
            
    except Exception as e:
        print(f"AI Advisory Error: {e}")
        # Proceed to TNAU-sourced static fallback

    # 2. STATIC FALLBACK - Load TNAU-sourced advisories from JSON
    if not ai_success:
        try:
            import random
            with open('data/farming_advisories.json', 'r', encoding='utf-8') as f:
                advisory_data = json.load(f)
            
            # Temperature-based advisory
            if temp > 38:
                temp_advs = advisory_data['temperature']['extreme_heat']
            elif temp >= 33:
                temp_advs = advisory_data['temperature']['hot']
            elif temp >= 25:
                temp_advs = advisory_data['temperature']['moderate']
            elif temp >= 18:
                temp_advs = advisory_data['temperature']['cool']
            else:
                temp_advs = advisory_data['temperature']['cold']
            
            # Pick one random advisory from the category
            idx = random.randint(0, len(temp_advs['en']) - 1)
            advisories.append({
                'en': temp_advs['en'][idx],
                'ta': temp_advs['ta'][idx]
            })
            
            # Humidity-based advisory
            if humidity > 85:
                hum_advs = advisory_data['humidity']['very_high']
            elif humidity >= 70:
                hum_advs = advisory_data['humidity']['high']
            elif humidity >= 40:
                hum_advs = advisory_data['humidity']['moderate']
            else:
                hum_advs = advisory_data['humidity']['low']
            
            idx = random.randint(0, len(hum_advs['en']) - 1)
            advisories.append({
                'en': hum_advs['en'][idx],
                'ta': hum_advs['ta'][idx]
            })
            
            # Rain-based advisory (only if rain detected)
            if rain_1h > 20:
                rain_advs = advisory_data['rain']['heavy_rain']
                idx = random.randint(0, len(rain_advs['en']) - 1)
                advisories.append({
                    'en': rain_advs['en'][idx],
                    'ta': rain_advs['ta'][idx]
                })
            elif rain_1h > 5:
                rain_advs = advisory_data['rain']['moderate_rain']
                idx = random.randint(0, len(rain_advs['en']) - 1)
                advisories.append({
                    'en': rain_advs['en'][idx],
                    'ta': rain_advs['ta'][idx]
                })
            elif rain_1h > 0:
                rain_advs = advisory_data['rain']['light_rain']
                idx = random.randint(0, len(rain_advs['en']) - 1)
                advisories.append({
                    'en': rain_advs['en'][idx],
                    'ta': rain_advs['ta'][idx]
                })
            
            # Wind-based advisory (only for significant wind)
            if wind_speed > 10:
                wind_advs = advisory_data['wind']['high_wind']
                idx = random.randint(0, len(wind_advs['en']) - 1)
                advisories.append({
                    'en': wind_advs['en'][idx],
                    'ta': wind_advs['ta'][idx]
                })
            elif wind_speed >= 5:
                wind_advs = advisory_data['wind']['moderate_wind']
                idx = random.randint(0, len(wind_advs['en']) - 1)
                advisories.append({
                    'en': wind_advs['en'][idx],
                    'ta': wind_advs['ta'][idx]
                })
                
        except Exception as e:
            print(f"Fallback Advisory Error: {e}")
            # Ultimate fallback if JSON fails
            advisories.append({
                'en': '✅ Check current conditions and plan field work accordingly.',
                'ta': '✅ தற்போதைய நிலையை சரிபார்த்து வயல் வேலைகளை திட்டமிடுங்கள்.'
            })

    return advisories






# ==================== PUBLIC ROUTES ====================
@app.route("/set_language", methods=["POST"])
def set_language():
    session.clear()
    selected_lang = request.form.get("lang")
    session["lang"] = selected_lang
    return redirect(request.referrer or url_for("home"))


def get_sowing_data(lang="en"):
    """Returns sowing data for all 12 months with localization"""
    data = {}
    
    # 1. Base English Data (Tamil Nadu Specific)
    base_en = {
        1: {"month": "January", "crops": ["Paddy (Navarai)", "Groundnut", "Blackgram"], "advice": "Ideal time for dry ploughing. Prepare lands for pulses."},
        2: {"month": "February", "crops": ["Sesame", "Cotton"], "advice": "Monitor for early pest signs. Apply neem oil if needed."},
        3: {"month": "March", "crops": ["Sorghum", "Cumbu", "Ragi"], "advice": "Summer ploughing is recommended after summer showers."},
        4: {"month": "April", "crops": ["Sesame", "Vegetables"], "advice": "Mulch your soil to conserve moisture during peak summer."},
        5: {"month": "May", "crops": ["Vegetables", "Green Manure"], "advice": "Sow green manure crops to fix nitrogen in soil for next season."},
        6: {"month": "June", "crops": ["Paddy (Kuruvai)", "Cotton"], "advice": "Kuruvai season begins. Ensure nursery preparation is done."},
        7: {"month": "July", "crops": ["Paddy (Kuruvai)", "Redgram", "Groundnut"], "advice": "Best month for rainfed groundnut sowing in many districts."},
        8: {"month": "August", "crops": ["Paddy (Samba)", "Tapioca", "Chillies"], "advice": "Samba nursery preparation should start now."},
        9: {"month": "September", "crops": ["Paddy (Samba)", "Maize", "Cotton"], "advice": "Main Samba planting season. Ensure proper water management."},
        10: {"month": "October", "crops": ["Paddy (Thaladi)", "Pulses"], "advice": "North East Monsoon begins. Ensure drainage channels are clear."},
        11: {"month": "November", "crops": ["Paddy (Thaladi)", "Groundnut"], "advice": "Watch out for fungal diseases due to high humidity."},
        12: {"month": "December", "crops": ["Groundnut", "Gingelly"], "advice": "Post-monsoon season. Ideal for oilseeds in rice fallows."}
    }

    # 2. Tamil Data
    base_ta = {
        1: {"month": "ஜனவரி", "crops": ["நெல் (நவரை)", "நிலக்கடலை", "உளுந்து"], "advice": "நிலத்தை உழுது பயறு வகை பயிரிட ஏற்ற நேரம்."},
        2: {"month": "பிப்ரவரி", "crops": ["எள்", "பருத்தி"], "advice": "பூச்சி தாக்குதலை கண்காணிக்கவும். தேவைப்பட்டால் வேப்பெண்ணெய் தெளிக்கவும்."},
        3: {"month": "மார்ச்", "crops": ["சோளம்", "கம்பு", "கேழ்வரகு"], "advice": "கோடை மழையைப் பயன்படுத்தி நிலத்தை உழுது வைக்கவும்."},
        4: {"month": "ஏப்ரல்", "crops": ["எள்", "காய்கறிகள்"], "advice": "கோடை காலத்தில் மண்ணின் ஈரப்பதத்தை காக்க மூடாக்கு இடவும்."},
        5: {"month": "மே", "crops": ["காய்கறிகள்", "பசுந்தாள் உரம்"], "advice": "மண் வளத்தை பெருக்க பசுந்தாள் உரப்பயிர்களை விதைக்கவும்."},
        6: {"month": "ஜூன்", "crops": ["நெல் (குறுவை)", "பருத்தி"], "advice": "குறுவை பருவம் தொடங்குகிறது. நாற்றங்கால் தயார் செய்யவும்."},
        7: {"month": "ஜூலை", "crops": ["நெல் (குறுவை)", "துவரை", "நிலக்கடலை"], "advice": "மானாவாரி நிலக்கடலை விதைப்புக்கு ஏற்ற மாதம்."},
        8: {"month": "ஆகஸ்ட்", "crops": ["நெல் (சம்பா)", "மரவள்ளி", "மிளகாய்"], "advice": "சம்பா பருவத்திற்கான நாற்றங்கால் தயாரிப்பைத் தொடங்கவும்."},
        9: {"month": "செப்டம்பர்", "crops": ["நெல் (சம்பா)", "மக்காச்சோளம்", "பருத்தி"], "advice": "சம்பா நடவுப் பருவம். முறையான நீர் மேலாண்மை அவசியம்."},
        10: {"month": "அக்டோபர்", "crops": ["நெல் (தாளடி)", "பயறு வகைகள்"], "advice": "வடகிழக்கு பருவமழை காலம். வடிகால் வசதியை உறுதி செய்யவும்."},
        11: {"month": "நவம்பர்", "crops": ["நெல் (தாளடி)", "நிலக்கடலை"], "advice": "ஈரப்பதம் அதிகம் இருப்பதால் பூஞ்சாண நோய்களை கண்காணிக்கவும்."},
        12: {"month": "டிசம்பர்", "crops": ["நிலக்கடலை", "எள்"], "advice": "பின் பருவமழை காலம். அரிசி தரிசில் எண்ணெய் வித்து பயிரிடலாம்."}
    }
    
    return base_ta if lang == "ta" else base_en


@app.route("/language", methods=["GET", "POST"])
def language():
    if request.method == "POST":
        session.permanent = True
        selected_lang = request.form.get("lang")
        session["lang"] = selected_lang
        return redirect(url_for("home"))
    return render_template("language.html")


@app.route("/")
def home():
    if "lang" not in session:
        return redirect(url_for("language"))
    
    t = load_language()
    lang = session.get("lang", "en")

    # 1. Daily Tip Logic
    from datetime import datetime
    day_of_year = datetime.now().timetuple().tm_yday
    tip_id = (day_of_year % 5) + 1
    
    # 2. Sowing Calendar Logic (Current Month Only)
    import datetime as dt
    now = dt.datetime.now()
    month_num = now.month
    
    full_calendar = get_sowing_data(lang)
    current_data = full_calendar.get(month_num)
    
    current_month = current_data["month"]
    recommended_crops = current_data["crops"]

    # 3. Fetch Agri News
    news_items = get_agri_news(lang)

    return render_template("index.html", t=t, tip_id=str(tip_id),
                         current_month=current_month, recommended_crops=recommended_crops,
                         news_items=news_items)


@app.route("/calendar")
def calendar():
    if "lang" not in session:
        return redirect(url_for("language"))
    t = load_language()
    lang = session.get("lang", "en")
    
    calendar_data = get_sowing_data(lang)
    
    # Pass as list sorted by month 1-12
    calendar_list = [calendar_data[i] for i in range(1, 13)]
    
    # Highlight current month
    import datetime as dt
    current_month_idx = dt.datetime.now().month - 1 # 0-indexed for template logic if needed
    
    return render_template("calendar.html", t=t, calendar=calendar_list, current_month_idx=current_month_idx)


@app.route("/about")
def about():
    if "lang" not in session:
        return redirect(url_for("language"))
    t = load_language()
    return render_template("about.html", t=t)


@app.route("/guide", methods=["GET", "POST"])
def guide():
    if "lang" not in session:
        return redirect(url_for("language"))

    t = load_language()

    if request.method == "POST":
        district = request.form["district"]
        crop = request.form["crop"]

        guide_data = get_crop_guide_from_db(district, crop)

        if guide_data:
            lang = session.get("lang", "en")

            result = {
                "crop": guide_data["crop_name_ta"] if lang == "ta" else guide_data["crop_name_en"],
                "district": guide_data["district_name_ta"] if lang == "ta" else guide_data["district_name_en"],
                "season": guide_data["season_ta"] if lang == "ta" else guide_data["season_en"],
                "soil": guide_data["soil_ta"] if lang == "ta" else guide_data["soil_en"],
                "explanation": guide_data["explanation_ta"] if lang == "ta" else guide_data["explanation_en"],
                "steps": [s[2] if lang == "ta" else s[1] for s in guide_data["steps"]]
            }

            session["guide_result"] = result

        else:
            session["guide_result"] = {
                "error": t.get("guide_not_found", "Guide data not found for this crop/district.")
            }

        return redirect(url_for("guide"))

    # Fetch dynamic dropdown options
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()

    # Get distinct districts
    cursor.execute("SELECT district, MAX(district_name_en), MAX(district_name_ta) FROM crop_guide GROUP BY district ORDER BY MAX(district_name_en)")
    districts = cursor.fetchall()

    # Get distinct crops
    cursor.execute("SELECT crop, MAX(crop_name_en), MAX(crop_name_ta) FROM crop_guide GROUP BY crop ORDER BY MAX(crop_name_en)")
    crops = cursor.fetchall()
    
    conn.close()

    result = session.pop("guide_result", None)

    return render_template("guide.html", t=t, result=result, districts=districts, crops=crops)


@app.route("/diagnose", methods=["GET", "POST"])
def diagnose():
    if "lang" not in session:
        return redirect(url_for("language"))
    
    t = load_language()
    result = None

    if request.method == "POST":
        image_file = request.files.get("image")
        
        if image_file:
            try:
                # Read image
                import PIL.Image
                img = PIL.Image.open(image_file)
                
                # Specialized Doctor Prompt
                doctor_prompt = (
                    "You are an expert Agricultural Plant Doctor. "
                    "Analyze this image carefully. "
                    "1. Identify the crop and any visible disease or pest. "
                    "2. If healthy, respond with JSON: {'status': 'healthy', 'message': 'The crop looks healthy.'} "
                    "3. If diseased, respond with JSON: {'status': 'issue', 'problem': 'Name of disease/pest', 'symptoms': 'Short list of visual symptoms', 'solution': 'Recommended chemical or organic cure'} "
                    "4. IMPORTANT: Respond ONLY in valid JSON format. "
                    f"5. Provide all text in {('Tamil' if session.get('lang') == 'ta' else 'English')}."
                )

                # Call Gemini Vision
                response = client.models.generate_content(
                    model="models/gemini-flash-lite-latest",
                    contents=[doctor_prompt, img]
                )
                
                # Convert image to base64 for display
                buffered = io.BytesIO()
                img.save(buffered, format="JPEG")
                img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
                
                # Parse JSON Response (Handling potential markdown fences)
                import json
                text = response.text.strip()
                if text.startswith("```json"):
                    text = text[7:-3]
                
                try:
                    data = json.loads(text)
                    if data.get('status') == 'healthy':
                        result = {
                            "problem": t['diagnose_healthy'],
                            "symptoms": "-",
                            "solution": "-",
                            "image_data": img_str
                        }
                    else:
                        result = {
                            "problem": data.get('problem', 'Unknown Issue'),
                            "symptoms": data.get('symptoms', 'N/A'),
                            "solution": data.get('solution', 'N/A'),
                            "image_data": img_str
                        }
                except json.JSONDecodeError:
                    # Fallback if AI fails to give JSON
                    result = {
                        "problem": "Analysis Warning",
                        "symptoms": "AI response format error.",
                        "solution": response.text,
                        "image_data": img_str
                    }

            except Exception as e:
                print(f"Diagnose Error: {e}")
                result = {
                    "problem": "System Error",
                    "symptoms": str(e),
                    "solution": "Please try again later."
                }

    return render_template("diagnose.html", t=t, result=result)


@app.route("/chatbot", methods=["GET", "POST"])
def chatbot():
    if "lang" not in session:
        return redirect(url_for("language"))
    
    # Initialize chat history if not present
    if "chat_history" not in session:
        session["chat_history"] = []
        
    t = load_language()

    if request.method == "POST":
        question = request.form.get("question")
        image_file = request.files.get("image")
        
        response_text = ""
        
        # Scenario 1: Image Upload (Plant Doctor)
        if image_file and image_file.filename != '':
            try:
                # Read image
                import PIL.Image
                img = PIL.Image.open(image_file)
                
                # Add to history (visual placeholder)
                display_text = f'''<div style="margin-bottom:5px;"><img src="static/uploads/{image_file.filename}" style="max-height: 150px; border-radius: 10px;"></div>'''
                if question:
                     display_text += f"<div>{question}</div>"
                else:
                     display_text += "<div>📷 Image uploaded for analysis</div>"
                
                # Note: valid path handling would require saving the file to static/uploads first or using base64.
                # Since we don't save files to disk in this simple demo, we will use a generic icon for history valid for session.
                # better approach for history:
                
                session["chat_history"].append({
                    "type": "user", 
                    "content": f"📷 [Image Analyzed]<br>{question if question else ''}"
                })
                
                # Construct Prompt
                doctor_prompt = (
                    "You are an expert Agricultural Plant Doctor. "
                    "Analyze this image carefully. "
                    "1. Identify the crop and any visible disease or pest. "
                    "2. If healthy, say 'The crop looks healthy'. "
                    "3. If diseased, provide the name, symptoms, and specific cure/medicine. "
                    "4. Answer in SHORT, CRISP text (bullets). "
                    f"Respond in {('Tamil' if session.get('lang') == 'ta' else 'English')}."
                )
                
                if question:
                    doctor_prompt += f"\nUser Question: {question}"

                # Call Gemini Vision
                response = client.models.generate_content(
                    model="models/gemini-flash-lite-latest",
                    contents=[doctor_prompt, img]
                )
                response_text = response.text
                
            except Exception as e:
                print(f"Vision Error: {e}")
                import traceback
                traceback.print_exc()
                response_text = f"Error analyzing image. Details: {str(e)}"

        # Scenario 2: Text Only
        elif question:
            # 1. Add User Question to History
            session["chat_history"].append({"type": "user", "content": question})
            
            # 2. Get AI Response (with conversation memory)
            response_text = get_chatbot_answer(question, session.get("chat_history", []))
            
        # 3. Add AI Response to History (formatted)
        if response_text:
            formatted = format_ai_response(response_text)
            session["chat_history"].append({
                "type": "bot", 
                "content": formatted, 
                "question": question if question else "Image Analysis"
            })
            
            # Prevent Cookie Bloat (Flask session limit is 4093 bytes)
            # Keep only the last 6 messages (3 QA pairs)
            if len(session["chat_history"]) > 6:
                session["chat_history"] = session["chat_history"][-6:]
                
            session.modified = True
            
        return redirect(url_for("chatbot"))

    return render_template("chatbot.html", t=t, chat_history=session["chat_history"])


@app.route("/clear_chat", methods=["POST"])
def clear_chat():
    """Clear the chat history"""
    session["chat_history"] = []
    session.modified = True
    return redirect(url_for("chatbot"))


@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    """Handle user feedback on chatbot answers"""
    data = request.get_json()
    question = data.get("question")
    feedback = data.get("feedback")
    
    if not question:
        return jsonify({"status": "error", "message": "No question provided"})

    # If feedback is negative, log it as an unanswered question for admin review
    if feedback == "negative":
        try:
            conn = sqlite3.connect("agri_support.db")
            cursor = conn.cursor()
            
            # Check if it already exists to avoid duplicates
            cursor.execute("SELECT id FROM unanswered_questions WHERE LOWER(question) = LOWER(?)", (question,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO unanswered_questions (question, created_at) VALUES (?, datetime('now'))", (question,))
                conn.commit()
                print(f"Logged unanswered question: {question}")
            
            conn.close()
        except Exception as e:
            print(f"Feedback Error: {e}")
            return jsonify({"status": "error"})

    # Update session history so it persists on reload
    if "chat_history" in session:
        for msg in session["chat_history"]:
            if msg.get("type") == "bot" and msg.get("question") == question:
                msg["feedback"] = feedback
                session.modified = True
                break

    return jsonify({"status": "success"})


@app.route("/pests", methods=["GET", "POST"])
def pests():
    if "lang" not in session:
        return redirect(url_for("language"))

    t = load_language()
    results = None
    selected_crop = None

    if request.method == "POST":
        selected_crop = request.form.get("crop")
        results = get_pest_disease_from_db(selected_crop, session.get("lang", "en"))

    # Fetch distinct crops for dropdown
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT crop FROM pest_disease ORDER BY crop")
    # Need to handle localization for crop names if possible, but schema only has 'crop' column
    # We will just pass the raw list for now
    crop_rows = cursor.fetchall()
    crops = [r[0] for r in crop_rows]
    conn.close()

    return render_template(
        "pests.html",
        results=results,
        crops=crops,
        selected_crop=selected_crop,
        t=t
    )


@app.route("/calculator", methods=["GET", "POST"])
def calculator():
    budget_result = None
    profit_result = None

    if request.method == "POST":
        calc_type = request.form.get("calc_type")

        if calc_type == "budget":
            area = float(request.form["area"])
            seed = float(request.form["seed_cost"])
            fertilizer = float(request.form["fertilizer_cost"])
            labour = float(request.form["labour_cost"])
            irrigation = float(request.form["irrigation_cost"])

            total_cost = area * (seed + fertilizer + labour + irrigation)
            budget_result = total_cost

        if calc_type == "profit":
            area = float(request.form["area"])
            yield_per_acre = float(request.form["yield"])
            price = float(request.form["price"])
            total_cost = float(request.form["total_cost"])

            income = area * yield_per_acre * price
            profit = income - total_cost

            profit_result = {
                "income": income,
                "profit": profit
            }

    return render_template(
        "calculator.html",
        budget_result=budget_result,
        profit_result=profit_result,
        t=load_language()
    )


@app.route("/crop-prices", methods=["GET", "POST"])
def crop_prices():
    t = load_language()

    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()

    result = None

    lang = session.get("lang", "en")
    district_col = "district_ta" if lang == "ta" else "district_en"
    crop_col = "crop_ta" if lang == "ta" else "crop_en"
    unit_col = "unit_ta" if lang == "ta" else "unit_en"

    if request.method == "POST":
        return redirect(url_for('crop_prices', district=request.form["district"], crop=request.form["crop"]))

    # Handle GET with parameters (Post-Redirect-Get Pattern)
    district = request.args.get("district")
    crop = request.args.get("crop")

    if district and crop:
        cursor.execute(f"""
            SELECT {district_col}, {crop_col}, price, {unit_col}, source, updated_on
            FROM crop_prices
            WHERE district_en = ? AND crop_en = ?
            ORDER BY updated_on DESC
            LIMIT 1
        """, (district, crop))

        row = cursor.fetchone()

        if row:
            result = {
                "district_key": district,
                "crop_key": crop,
                "district": row[0],
                "crop": row[1],
                "price": row[2],
                "unit": row[3],
                "source": row[4],
                "updated_on": row[5]
            }

    # Fetch dynamic dropdown options
    # We need to fetch distinct available districts and crops    # Get distinct districts
    cursor.execute("SELECT district_en, MAX(district_ta) FROM crop_prices GROUP BY district_en ORDER BY district_en")
    districts = cursor.fetchall()

    cursor.execute("SELECT crop_en, MAX(crop_ta) FROM crop_prices GROUP BY crop_en ORDER BY crop_en")
    crops = cursor.fetchall()

    conn.close()
    return render_template("crop_prices.html", result=result, t=t, districts=districts, crops=crops)


@app.route("/price-history", methods=["POST"])
def price_history():
    district = request.form["district"]
    crop = request.form["crop"]

    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT updated_on, price
        FROM crop_prices
        WHERE district_en = ? AND crop_en = ?
        ORDER BY updated_on
    """, (district, crop))

    rows = cursor.fetchall()
    conn.close()

    dates = [r[0] for r in rows]
    prices = [float(r[1]) for r in rows]

    return jsonify({
        "dates": dates,
        "prices": prices,
        "district": district,
        "crop": crop
    })


@app.route("/get-crops", methods=["GET"])
def get_crops():
    district = request.args.get("district")
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()
    
    # If district is selected, filter crops available in that district
    if district:
        cursor.execute("SELECT crop_en, MAX(crop_ta) FROM crop_prices WHERE district_en = ? GROUP BY crop_en ORDER BY crop_en", (district,))
    else:
        cursor.execute("SELECT crop_en, MAX(crop_ta) FROM crop_prices GROUP BY crop_en ORDER BY crop_en")
        
    crops = cursor.fetchall()
    conn.close()
    
    # Convert to list of dicts for JSON
    crop_list = [{"en": c[0], "ta": c[1]} for c in crops]
    return jsonify(crop_list)


@app.route("/weather", methods=["GET", "POST"])
def weather():
    if "lang" not in session:
        return redirect(url_for("language"))

    t = load_language()

    conn = sqlite3.connect('agri_support.db')
    cursor = conn.cursor()

    # Fetch available districts
    cursor.execute("SELECT district_en, district_ta FROM district_coordinates ORDER BY district_en")
    districts = cursor.fetchall()

    result = None

    if request.method == "POST":
        district = request.form.get('district')

        # Get coordinates
        cursor.execute("SELECT latitude, longitude, district_en, district_ta FROM district_coordinates WHERE district_en = ?", (district,))
        district_info = cursor.fetchone()

        if district_info:
            lat = district_info[0]
            lon = district_info[1]

            try:
                # Fetch current weather
                # Pass 'lang' parameter for localized description
                lang_code = session.get("lang", "en")
                current_url = f"{OPENWEATHER_BASE_URL}/weather?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang={lang_code}"
                current_response = requests.get(current_url)
                weather_data = current_response.json()

                # Fetch 5-day forecast
                forecast_url = f"{OPENWEATHER_BASE_URL}/forecast?lat={lat}&lon={lon}&appid={OPENWEATHER_API_KEY}&units=metric&lang={lang_code}"
                forecast_response = requests.get(forecast_url)
                forecast_data = forecast_response.json()

                # Override OpenWeatherMap's micro-location with our exact District Name
                weather_data['name'] = district_info[3] if lang_code == 'ta' else district_info[2]

                # Generate advisories
                advisories = generate_advisories(weather_data, session.get("lang", "en"))

                # Local Translation Mapping for Tamil
                weather_trans = {
                    "clear sky": "தெளிவான வானம்",
                    "few clouds": "சில மேகங்கள்",
                    "scattered clouds": "சிதறிய மேகங்கள்",
                    "broken clouds": "மேகமூட்டம்",
                    "shower rain": "மழைத்தூறல்",
                    "rain": "மழை",
                    "thunderstorm": "இடியுடன் கூடிய மழை",
                    "snow": "பனி",
                    "mist": "மூடுபனி",
                    "haze": "பனிமூட்டம்",
                    "overcast clouds": "மேகமூட்டம்",
                    "light rain": "லேேசான மழை",
                    "moderate rain": "மிதமான மழை",
                    "heavy intensity rain": "கனமழை",
                    "smoke": "புகை மூட்டம்",
                    "drizzle": "தூறல்"
                }

                # Helper to translate description
                def translate_desc(desc, code):
                    if code == 'ta':
                        return weather_trans.get(desc.lower(), desc)
                    return desc.title()

                # Translate Current Weather
                if lang_code == 'ta':
                    weather_data['weather'][0]['description'] = translate_desc(weather_data['weather'][0]['description'], 'ta')

                # Using loop for forecast
                daily_forecast = []
                seen_dates = set()
                
                for item in forecast_data['list']:
                    # Translate Forecast Item
                    if lang_code == 'ta':
                         item['weather'][0]['description'] = translate_desc(item['weather'][0]['description'], 'ta')

                    dt_txt = item['dt_txt']
                    date_str = dt_txt.split(" ")[0]
                    time_str = dt_txt.split(" ")[1]
                    
                    if date_str not in seen_dates:
                        # Prefer noon forecast if possible, or take the first one available for the new date
                        if "12:00:00" in time_str or date_str != datetime.now().strftime('%Y-%m-%d'):
                            daily_forecast.append(item)
                            seen_dates.add(date_str)
                            
                            # Limit to 5 days
                            if len(daily_forecast) >= 5:
                                break

                # Store in session for PRG pattern
                session["weather_result"] = {
                    "district_en": district_info[2],
                    "district_ta": district_info[3],
                    "weather": weather_data,
                    "forecast": {"list": daily_forecast},
                    "advisories": advisories,
                    "selected_district": district
                }

            except Exception as e:
                print(f"Weather API Error: {e}")
                # Set error message for the template
                result = {
                    "error": t.get("weather_check_network", "Network Error"),
                    "district_en": district_info[2],
                    "district_ta": district_info[3],
                    "selected_district": district
                }
                session["weather_result"] = result

        conn.close()
        return redirect(url_for("weather"))

    # Get result from session (PRG pattern)
    result = session.pop("weather_result", None)

    # Fetch all district coordinates for GPS feature
    cursor.execute("SELECT district_en, latitude, longitude FROM district_coordinates")
    districts_data = [{"name": row[0], "lat": row[1], "lon": row[2]} for row in cursor.fetchall()]

    conn.close()
    return render_template('weather.html', t=t, districts=districts, result=result, districts_data=districts_data)



def init_db():
    conn = sqlite3.connect('agri_support.db')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            category TEXT,
            rating INTEGER,
            message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Pending'
        )
    """)
    conn.commit()
    conn.close()

# Initialize DB
init_db()




# ==================== ADMIN ROUTES ====================
@app.route("/login", methods=["GET", "POST"])
def login():
    # Force English for Admin Interface
    session["lang"] = "en"
    t = load_language()

    if request.method == "POST":
        password = request.form.get("password")

        # Admin password loaded from .env
        if password == os.getenv("ADMIN_PASSWORD", "admin123"):
            session["is_admin"] = True
            return redirect(url_for("admin"))
        else:
            return render_template("login.html", error=f"❌ {t.get('invalid_password', 'Invalid Password!')}", t=t)

    return render_template("login.html", t=t)


@app.route("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("home"))


@app.route("/admin")
def admin():
    # Force English for Admin Interface
    session["lang"] = "en"
    t = load_language()

    # SECURITY CHECK
    if not session.get("is_admin"):
        return redirect(url_for("login"))

    # Connect to database
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()

    # Fetch all unanswered questions (Newest first)
    cursor.execute("SELECT id, question, created_at FROM unanswered_questions ORDER BY created_at DESC")
    questions = cursor.fetchall()

    # Fetch all Feedback (Newest first)
    cursor.execute("SELECT id, name, category, rating, message, created_at FROM feedback ORDER BY created_at DESC")
    feedbacks = cursor.fetchall()

    conn.close()

    return render_template("admin.html", questions=questions, feedbacks=feedbacks, t=t)


@app.route("/delete_question/<int:id>", methods=["POST"])
def delete_question(id):
    # 1. Connect to database
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()

    # 2. Delete the specific question by ID
    cursor.execute("DELETE FROM unanswered_questions WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    # 3. Reload the admin page
    return redirect(url_for("admin"))


@app.route("/admin/chatbot", methods=["GET", "POST"])
def admin_chatbot():
    if not session.get("is_admin"): return redirect(url_for("login"))
    if "lang" not in session: return redirect(url_for("language"))
    t = load_language()

    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()

    # Handle New Rule
    if request.method == "POST":
        k_en = request.form.get("keyword_en")
        k_ta = request.form.get("keyword_ta")
        a_en = request.form.get("answer_en")
        a_ta = request.form.get("answer_ta")
        
        cursor.execute("INSERT INTO chatbot_qa (keyword_en, keyword_ta, answer_en, answer_ta) VALUES (?, ?, ?, ?)",
                       (k_en, k_ta, a_en, a_ta))
        conn.commit()
    
    # Fetch all rules
    cursor.execute("SELECT id, keyword_en, keyword_ta, answer_en, answer_ta FROM chatbot_qa")
    qa_pairs = cursor.fetchall()
    conn.close()

    return render_template("admin_chatbot.html", t=t, qa_pairs=qa_pairs)


@app.route("/admin/prices", methods=["GET", "POST"])
def admin_prices():
    if not session.get("is_admin"): return redirect(url_for("login"))
    if "lang" not in session: return redirect(url_for("language"))
    t = load_language()
    
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()

    if request.method == "POST":
        district = request.form.get("district")
        crop = request.form.get("crop")
        price = request.form.get("price")
        source = request.form.get("source", "Manual Entry")
        
        if district and crop and price:
            cursor.execute("""
                INSERT OR REPLACE INTO crop_prices (district_en, district_ta, crop_en, crop_ta, price, unit_en, unit_ta, source, updated_on) 
                VALUES (?, ?, ?, ?, ?, 'Quintal', 'குவிண்டால்', ?, DATE('now'))
            """, (district, district, crop, crop, price, source))
            conn.commit()

    # Fetch recent prices
    cursor.execute("SELECT id, district_en, crop_en, price, unit_en, source, updated_on FROM crop_prices ORDER BY updated_on DESC LIMIT 50")
    prices = cursor.fetchall()
    conn.close()

    return render_template("admin_prices.html", t=t, prices=prices)


@app.route("/delete_price/<int:id>", methods=["POST"])
def delete_price(id):
    if not session.get("is_admin"): return redirect(url_for("login"))
    conn = sqlite3.connect("agri_support.db")
    conn.execute("DELETE FROM crop_prices WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_prices"))


@app.route("/delete_chatbot_qa/<int:id>", methods=["POST"])
def delete_chatbot_qa(id):
    if not session.get("is_admin"): return redirect(url_for("login"))
    conn = sqlite3.connect("agri_support.db")
    conn.execute("DELETE FROM chatbot_qa WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_chatbot"))


@app.route("/admin/guide", methods=["GET", "POST"])
def admin_guide():
    if "lang" not in session: return redirect(url_for("language"))
    t = load_language()
    if not session.get("is_admin"): return redirect(url_for("login"))
    
    return render_template("admin_guide.html", t=t)


@app.route("/admin/add_guide", methods=["POST"])
def add_guide():
    if not session.get("is_admin"): return redirect(url_for("login"))
    
    conn = sqlite3.connect("agri_support.db")
    cursor = conn.cursor()
    
    try:
        # 1. Insert Guide Head
        cursor.execute("""
            INSERT INTO crop_guide (district, district_name_en, district_name_ta, crop, crop_name_en, crop_name_ta, season_en, season_ta, soil_en, soil_ta, explanation_en, explanation_ta)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Cultivation Guide', 'சாகுபடி வழிகாட்டி')
        """, (
            request.form["district_en"], request.form["district_en"], request.form["district_ta"],
            request.form["crop_en"], request.form["crop_en"], request.form["crop_ta"],
            request.form["season_en"], request.form["season_ta"],
            request.form["soil_en"], request.form["soil_ta"]
        ))
        
        # 2. Insert Steps
        steps_en = request.form.getlist("step_en[]")
        steps_ta = request.form.getlist("step_ta[]")
        
        for i, (s_en, s_ta) in enumerate(zip(steps_en, steps_ta)):
             cursor.execute("INSERT INTO crop_guide_steps (district, crop, step_no, step_en, step_ta) VALUES (?, ?, ?, ?, ?)",
                            (request.form["district_en"], request.form["crop_en"], i+1, s_en, s_ta))
                            
        conn.commit()
    except Exception as e:
        print(f"Guide Add Error: {e}")
        conn.rollback()
        
    conn.close()
    return redirect(url_for("admin_guide"))


@app.route("/admin/pests", methods=["GET"])
def admin_pests():
    if "lang" not in session: return redirect(url_for("language"))
    t = load_language()
    if not session.get("is_admin"): return redirect(url_for("login"))
    
    return render_template("admin_pests.html", t=t)


@app.route("/admin/add_pest", methods=["POST"])
def add_pest():
    if not session.get("is_admin"): return redirect(url_for("login"))
    
    try:
        import os
        from werkzeug.utils import secure_filename
        
        image = request.files['image']
        filename = secure_filename(image.filename)
        # Unique name
        import time
        unique_name = f"{int(time.time())}_{filename}"
        
        # Save to 'static/pests' directory
        save_dir = os.path.join(app.root_path, 'static/pests')
        os.makedirs(save_dir, exist_ok=True)
        
        save_path = os.path.join(save_dir, unique_name)
        image.save(save_path)
        
        conn = sqlite3.connect("agri_support.db")
        conn.execute("""
            INSERT INTO pest_disease (crop, name_en, name_ta, category, symptoms_en, symptoms_ta, precautions_en, precautions_ta, solutions_en, solutions_ta, image)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["crop"],
            request.form["name_en"], request.form["name_ta"],
            request.form["category"],
            request.form["symptoms_en"], request.form["symptoms_ta"],
            "-", "-", # precautions placeholder
            request.form["solutions_en"], request.form["solutions_ta"],
            f"/static/uploads/{unique_name}"
        ))
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Pest Add Error: {e}")
        
    return redirect(url_for("admin_pests"))






@app.route("/transcribe_audio", methods=["POST"])
def transcribe_audio():
    """Transcribe audio using Gemini"""
    try:
        import os
        import tempfile
        import google.generativeai as genai
        
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

        if 'audio' not in request.files:
            return jsonify({"error": "No audio file provided"}), 400
        
        audio_file = request.files['audio']
        
        fd, temp_path = tempfile.mkstemp(suffix=".webm")
        os.close(fd) 
        
        audio_data = audio_file.read()
        
        if len(audio_data) == 0:
             return jsonify({"error": "Empty audio file received"}), 400

        model = genai.GenerativeModel("models/gemini-flash-lite-latest")
        
        inline_audio = {
            "mime_type": "audio/webm",
            "data": audio_data
        }
        
        response = model.generate_content([
            "Transcribe this audio faithfully. Return ONLY the text spoken, no markdown, no quotes. If audio is unclear, return empty string.",
            inline_audio
        ])
        
        try:
            os.remove(temp_path)
        except:
            pass
        
        return jsonify({"text": response.text.strip()})
        
    except Exception as e:
        print(f"Transcription Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    if "lang" not in session: return redirect(url_for("language"))
    t = load_language()
    
    if request.method == "POST":
        try:
            # Handle both JSON and Form Data
            if request.is_json:
                data = request.json
                name = data.get("name")
                category = data.get("category")
                rating = int(data.get("rating"))
                message = data.get("message")
            else:
                name = request.form.get("name")
                category = request.form.get("category")
                rating = int(request.form.get("rating"))
                message = request.form.get("message")
            
            conn = sqlite3.connect("agri_support.db")
            conn.execute("INSERT INTO feedback (name, category, rating, message) VALUES (?, ?, ?, ?)",
                         (name, category, rating, message))
            conn.commit()
            conn.close()
            
            # Send Email Notification
            send_feedback_email(name, category, rating, message)
            
            return jsonify({"status": "success", "message": "Feedback submitted successfully"})
            
        except Exception as e:
            print(f"Feedback Error: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500

    return render_template("feedback.html", t=t)


@app.route("/offline")
def offline():
    t = load_language()
    return render_template("offline.html", t=t)

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
