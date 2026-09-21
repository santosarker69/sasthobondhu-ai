from flask import Flask, render_template, request, jsonify, session
import json
from gtts import gTTS
import speech_recognition as sr
from pydub import AudioSegment
import os
from dotenv import load_dotenv
load_dotenv()
_gemini_client = None

def get_gemini_client():
    global _gemini_client

    if _gemini_client is not None:
        return _gemini_client

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    try:
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
        return _gemini_client
    except Exception as e:
        print("❌ GEMINI CLIENT CREATION FAILED")
        print("ERROR TYPE:", type(e).__name__)
        print("ERROR:", e)
        return None


def gemini_semantic_match(user_message):
    """
    Ask Gemini to map an unmatched user message to ONE condition that already
    exists in disease_data.json. Gemini does not generate the medical answer;
    Python + disease_data.json still generates the response.
    """
    client = get_gemini_client()
    if client is None:
        return None

    # Send only the fields needed for semantic matching.
    compact_database = {}
    for disease_key, disease_info in disease_data.items():
        compact_database[disease_key] = {
            "keywords": disease_info.get("keywords", []),
            "possible_conditions": disease_info.get("possible_conditions", []),
            "emergency": disease_info.get("emergency", False)
        }

    prompt = f"""
You are the semantic interpretation layer of SasthoBondhu AI.

Your job is NOT to diagnose the user and NOT to write a medical answer.

Read the user's message and choose the best matching condition ONLY from the
provided disease database.

Rules:
1. Return a disease_key only if the user's symptoms are reasonably consistent
   with that condition.
2. You may understand different wording, synonyms, sentence structure,
   English/Bangla wording, and phrases such as "pain in my left chest" when
   the database contains a corresponding condition.
3. Never invent a new disease key.
4. If none of the database conditions is a reasonable match, return null.
5. Do not use the emergency flag to invent a match.
6. Do not diagnose; this is only semantic classification.

User message:
{user_message}

Disease database:
{json.dumps(compact_database, ensure_ascii=False)}
"""

    schema = {
        "type": "object",
        "properties": {
            "matched_disease": {
                "type": "STRING",
                "description": "One exact disease key from the supplied database. Return an empty string if there is no reasonable match."
            }
        },
        "required": ["matched_disease"]
    }

    try:
        from google.genai import types

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0
            )
        )

        result = json.loads(response.text)
        matched_key = result.get("matched_disease", "").strip()

        if matched_key in disease_data:
            return [(matched_key, disease_data[matched_key])]

        return None

    except Exception as e:
        print("❌ GEMINI SEMANTIC FALLBACK FAILED")
        print("ERROR TYPE:", type(e).__name__)
        print("ERROR:", e)
        return None


def get_disease_data_with_gemini(user_message):
    """
    Local keyword matching always runs first.
    Gemini is called only when local matching returns nothing.
    """
    matched = get_disease_data(user_message)

    if matched:
        return matched

    return gemini_semantic_match(user_message)


chat_history = []
user_data = {
    "active": False,
    "step": "",
    "location": "",
    "name": "",
    "mode": "",
    "language": "bn"   
}
ticket_data = {
    "total_tickets": 0
}
# =========================
# DASHBOARD DATA
# =========================

dashboard_data = {
    "total_users": 0,
    "total_reports": 0
}

# disease_data.json থেকে automatically সব disease নেওয়া হবে
disease_stats = {}

# District-wise total statistics
district_stats = {
    "Dhaka": 0,
    "Narayanganj": 0,
    "Noakhali": 0,
    "Cumilla": 0,
    "Chattogram": 0,
    "Rajshahi": 0,
    "Sylhet": 0,
    "Hatiya": 0,
    "Siddhirganj": 0,
    "Fatullah": 0,
    "Kanchpur": 0,
    "Chankharpool": 0,
    "Unknown": 0
}

# Disease + District statistics
# Example:
# {
#     "জ্বর": {
#         "Dhaka": 2,
#         "Narayanganj": 5
#     }
# }
disease_location_stats = {}

recent_chats = []
app = Flask(__name__)
app.secret_key = "sasthobondhu-secret-key"

def load_language(language):
    path = os.path.join(
        app.static_folder,
        "languages",
        f"{language}.json"
    )

    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(
            os.path.join(app.static_folder, "languages", "bn.json"),
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

def get_text(language, key, **kwargs):
    lang_data = load_language(language)

    text = lang_data.get(key, "")

    if kwargs:
        text = text.format(**kwargs)

    return text

import os

with open("hospitals.json", "r",encoding="utf-8") as file:
    hospitals = json.load(file)
with open("data/disease_data.json", "r", encoding="utf-8") as file:
    disease_data = json.load(file)

# =========================
# INITIALIZE DISEASE STATS
# =========================

for disease_key in disease_data.keys():
    disease_stats[disease_key] = 0
    disease_location_stats[disease_key] = {}

def find_disease_response(user_message):
    user_message = user_message.strip().lower()

    for disease_name, data in disease_data.items():
        for keyword in data["keywords"]:
            if keyword.lower() in user_message:
                return data

    return None
    
district_map = {
        "ঢাকা": "Dhaka",
        "ঢাকায়": "Dhaka",
        "নারায়ণগঞ্জ": "Narayanganj",
        "নারায়ণগঞ্জ": "Narayanganj",
        "নারায়ণগঞ্জে": "Narayanganj",
        "চট্টগ্রাম": "Chattogram",
        "চট্টগ্রামে": "Chattogram",
        "নোয়াখালী": "Noakhali",
        "নোয়াখালীতে": "Noakhali",
        "ঢাকাতে": "Dhaka",
        "কুমিল্লাতে": "Cumilla",
        "কুমিল্লায়": "Cumilla",
        "কুমিল্লা": "Cumilla",
        "রাজশাহী": "Rajshahi",
        "রাজশাহীতে": "Rajshahi",
        "রাজশাহীর": "Rajshahi",
        "সিলেট": "Sylhet",
        "সিলেটে": "Sylhet",
        "হাতিয়া": "Hatiya",
        "হাতিয়া": "Hatiya",

        "সিদ্ধিরগঞ্জ": "Siddhirganj",
        "হীরাঝিল": "Siddhirganj",
        "হিরাঝিল": "Siddhirganj",
    
        "ফতুল্লা": "Fatullah",
        "ফতুল্লায়": "Fatullah",
        "ফতুল্লায়": "Fatullah",

        "কাঁচপুর": "Kanchpur",
        "কাচপুর": "Kanchpur",
    
        "চাঁনখারপুল": "Chankharpool",
        "চানখারপুল": "Chankharpool",
        "চাংখারপুর": "Chankharpool",
        "চাখারপুল": "Chankharpool",
        "চাংখারপুল": "Chankharpool"
    } 

regional_words = {

    # Noakhali Common Words

    "মোর": "আমার",
    "মুই": "আমি",
    "তোর": "তোমার",
    "তুঁই": "তুমি",

    "পোলা": "ছেলে",
    "মাইয়া": "মেয়ে",

    "গা জ্বলে": "জ্বর",
    "গা গরম": "জ্বর",

    "মাথা ধরছে": "মাথা ব্যথা",
    "গলা ব্যাদা": "গলা ব্যথা",

    "হাঁচি আইতাছে": "হাঁচি হচ্ছে",
    "কাশি আইতাছে": "কাশি হচ্ছে",

    "খাইতে পারতাছি না": "খেতে পারছি না",
    "ঘুম অইতাছে না": "ঘুম হচ্ছে না",

    "ব্যাদা": "ব্যথা",

    "অইতাছে": "হচ্ছে",
    "আইছে": "এসেছে",
    "গেইছে": "গিয়েছে",

    "কই": "কোথায়",
    "কইরা": "করে",

    "ডর": "ভয়",
    "ডর লাগতাছে": "ভয় লাগছে"
}
noakhali_reply_words = {
    "মোর": "আমার",
    "গা গরম": "জ্বর",
    "অইছে": "হয়েছে",

    # Long phrases first
    "ভয় পাওয়ার কিছু নেই": "ডরাইয়েন না",
    "আপনার বাসা থেকে সবচেয়ে কাছে হলো": "আপনের বাসা থন হদ্দে কাছে হইলো",
    "আপনার বাসা থেকে": "আপনের বাসা থন",
    "সবচেয়ে কাছে": "হদ্দে কাছে",

    # Hospitals
    "ডাক্তার দেখান": "ডাক্তার দেহান",
    "টিকেট কাটবেন": "টিকেট কাডেন",
    "টিকেটের দাম": "টিকেটের দাম",
    "তারপর": "হেরপর",

    # Common words
    "আপনার": "আপনের",
    "আপনি": "আপনে",
    "সেখানে": "হিয়ানে",
    "ঐখানে": "হিয়ানে",
    "হাসপাতালে": "হাসপাতালত",
    "হবে": "অইবো",
    "হচ্ছে": "অইতাছে",
    "যাবেন": "যাইয়েন",
    "যান": "যাইয়েন",
    "টাকা": "টেহা",
    "নেই": "নাই",
    "বলুন": "কন",
    "কথা": "কাথা",
    "থেকে": "থন"
}

def get_disease_data(user_message):

    user_message = user_message.lower().strip()

    matched_diseases = []

    # ---------------- HAM SPECIAL CONDITION ----------------

    has_fever = any(
        word in user_message
        for word in [
            "জ্বর",
            "জ্বর হয়েছে",
            "জ্বর হয়েছে",
            "জ্বর আছে"
        ]
    )

    has_rash = any(
        word in user_message
        for word in [
            "ফুসকুড়ি",
            "ফুসকুড়ি",
            "মুখে ফুসকুড়ি",
            "মুখে ফুসকুড়ি"
        ]
    )

    ham_matched = has_fever and has_rash


    # ---------------- DISEASE MATCHING ----------------

    for disease_key, disease_info in disease_data.items():

        # Ham
        if disease_key == "হাম":

            if ham_matched:

                matched_diseases.append(
                    (disease_key, disease_info)
                )

            continue


        # যদি Ham match করে থাকে,
        # তাহলে generic "জ্বর" disease বাদ দিচ্ছি
        if ham_matched and disease_key == "জ্বর":

            continue


        # ---------------- NORMAL DISEASES ----------------

        keywords = disease_info.get("keywords", [])

        for keyword in keywords:

            if keyword.lower() in user_message:

                matched_diseases.append(
                    (disease_key, disease_info)
                )

                break


    return matched_diseases

def get_localized_disease_text(disease_info, language, field):
    translations = disease_info.get("translations", {})

    if language in translations:
        return translations[language].get(
            field,
            disease_info.get(field, "")
        )

    return disease_info.get(field, "")

def get_hospital_by_district(user_message):

    user_message = user_message.lower().strip()

    # Bangla + English location names
    location_map = {
        "ঢাকা": "Dhaka",
        "dhaka": "Dhaka",

        "নারায়ণগঞ্জ": "Narayanganj",
        "নারায়ণগঞ্জ": "Narayanganj",
        "narayanganj": "Narayanganj",

        "চট্টগ্রাম": "Chattogram",
        "চট্টগ্রামে": "Chattogram",
        "chattogram": "Chattogram",
        "chittagong": "Chattogram",

        "নোয়াখালী": "Noakhali",
        "নোয়াখালী": "Noakhali",
        "noakhali": "Noakhali",

        "কুমিল্লা": "Cumilla",
        "কুমিল্লায়": "Cumilla",
        "কুমিল্লায়": "Cumilla",
        "cumilla": "Cumilla",
        "comilla": "Cumilla",

        "সিলেট": "Sylhet",
        "সিলেটে": "Sylhet",
        "sylhet": "Sylhet",

        "রাজশাহী": "Rajshahi",
        "রাজশাহীতে": "Rajshahi",
        "rajshahi": "Rajshahi",

        "হাতিয়া": "Hatiya",
        "হাতিয়া": "Hatiya",
        "hatiya": "Hatiya",

        "সিদ্ধিরগঞ্জ": "Siddhirganj",
        "সিদ্ধিরগঞ্জে": "Siddhirganj",
        "siddhirganj": "Siddhirganj",

        "ফতুল্লা": "Fatullah",
        "ফতুল্লায়": "Fatullah",
        "ফতুল্লায়": "Fatullah",
        "fatullah": "Fatullah",

        "কাঁচপুর": "Kanchpur",
        "কাচপুর": "Kanchpur",
        "কাঁচপুরে": "Kanchpur",
        "কাচপুরে": "Kanchpur",
        "kanchpur": "Kanchpur",

        "চাঁনখারপুল": "Chankharpool",
        "চানখারপুল": "Chankharpool",
        "chankharpool": "Chankharpool",
        "chankharpul": "Chankharpool"
    }

    for location, district in location_map.items():

        if location in user_message:

            for hospital in hospitals:

                if hospital["district"].lower() == district.lower():

                    return hospital

    return None

fallback_data = {
    "জ্বর": "জ্বর সাধারণ ভাইরাল সংক্রমণ বা অন্য কারণে হতে পারে। পর্যাপ্ত বিশ্রাম নিন এবং সমস্যা বাড়লে চিকিৎসকের পরামর্শ নিন।",

    "কাশি": "কাশি সাধারণ ঠান্ডা, এলার্জি বা সংক্রমণের কারণে হতে পারে। দীর্ঘস্থায়ী হলে ডাক্তারের পরামর্শ নিন।",

    "মাথা ব্যথা": "মাথা ব্যথা ক্লান্তি, ঘুমের অভাব বা অন্য কারণে হতে পারে। বিশ্রাম নিন এবং সমস্যা বাড়লে চিকিৎসকের পরামর্শ নিন।",

    "পেট ব্যথা": "পেট ব্যথা হজমজনিত সমস্যা বা অন্য কারণে হতে পারে। তীব্র হলে চিকিৎসকের পরামর্শ নিন।",

    "বুক ব্যথা": "বুক ব্যথা গুরুত্বের সাথে নিতে হবে। দ্রুত নিকটস্থ হাসপাতালে যোগাযোগ করুন।",

    "শ্বাসকষ্ট": "শ্বাসকষ্ট হলে দ্রুত চিকিৎসা নেওয়া প্রয়োজন।",

    "ডায়রিয়া": "প্রচুর পানি পান করুন এবং প্রয়োজন হলে চিকিৎসকের পরামর্শ নিন।",

    "বমি": "শরীরে পানিশূন্যতা এড়াতে পর্যাপ্ত তরল গ্রহণ করুন।",
    
    "সাপ": "সাপে কাটলে কোনো ওঝা বা ঝাড়ফুঁকের উপর নির্ভর করবেন না। আক্রান্ত ব্যক্তিকে যত দ্রুত সম্ভব নিকটস্থ হাসপাতালে নিয়ে যান। আক্রান্ত অঙ্গটি যতটা সম্ভব স্থির রাখুন এবং অপ্রয়োজনীয়ভাবে হাঁটাচলা করাবেন না। ক্ষত কাটা, বিষ চুষে বের করা বা শক্ত করে দড়ি বাঁধবেন না।",

    "গলা ব্যথা": "গলা ব্যথা সংক্রমণ বা ঠান্ডার কারণে হতে পারে।",

    "দুর্বলতা": "পর্যাপ্ত বিশ্রাম ও পুষ্টিকর খাবার গ্রহণ করুন।"
}
def convert_to_noakhali(reply):

    for normal, local in noakhali_reply_words.items():

        reply = reply.replace(normal, local)

    return reply

def create_audio(reply, language="bn"):

    import uuid

    audio_file = (
        f"reply_{uuid.uuid4().hex}.mp3"
    )

    tts_language = "en" if language == "en" else "bn"

    tts = gTTS(
        text=reply,
        lang=tts_language,
        slow=False
    )

    tts.save(
        f"static/{audio_file}"
    )

    return audio_file

def speech_to_text(audio_path):

    sound = AudioSegment.from_file(audio_path)

    sound.export("voice.wav", format="wav")

    recognizer = sr.Recognizer()

    with sr.AudioFile("voice.wav") as source:

        audio = recognizer.record(source)

    try:

        text = recognizer.recognize_google(
            audio,
            language="bn-BD"
        )

        return text

    except:

        return ""



@app.route("/", methods=["GET", "POST"])
def home():
    reply = ""
    hospital_name = ""
    hospital_beds = ""
    audio_file = None

    # Saved language ব্যবহার করবে
    language = user_data.get("language", "bn")

    if request.method == "POST":

        user_message = request.form["message"]

        # যদি form থেকে language আসে, সেটি save করবে
        form_language = request.form.get("language")

        if form_language in ["bn", "en", "fr"]:
            language = form_language
            session["language"] = language
            user_data["language"] = language
        else:
            # না এলে আগের selected language ব্যবহার করবে
            language = session.get("language", "bn")
            user_data["language"] = language

        print("Selected language:", language)

        original_message = user_message
        for local_word, normal_word in regional_words.items():

            if local_word in user_message:

                user_message = user_message.replace(
                    local_word,
                    normal_word
                )
        is_noakhali = False

        for word in regional_words:

            if word in original_message:

                is_noakhali = True
                break

        import re

        lower_message = user_message.lower().strip()

        greeting_words = [
            "hello",
            "hi",
            "hey",
            "health",
            "sasthobondhu",
            "sastho bondhu",
            "bonjour",
            "salut"
        ]

        bangla_greetings = [
            "হ্যালো",
            "স্বাস্থ্যবন্ধু",
            "স্বাস্থ্য বন্ধু",
            "হ্যালো স্বাস্থ্যবন্ধু",
            "হ্যালো স্বাস্থ্য বন্ধু"
        ]

        is_greeting = (
            any(
                re.search(rf"\b{re.escape(word)}\b", lower_message)
                for word in greeting_words
            )
            or
            any(word in lower_message for word in bangla_greetings)
        )

        if is_greeting:
            user_data["mode"] = "flow"      
            user_data["active"] = True
            user_data["step"] = "name"

            reply = get_text(language, "ask_name")
            audio_file = create_audio(reply, language)

            chat_history.append({
                "user": original_message,
                "ai": reply
            })

            return render_template(
                "index.html",
                chat_history=chat_history,
                language=language,
                audio_file=audio_file
            )
        
        if (
            user_data["active"]
            and user_data["step"] == "name"
        ):

            name_text = original_message.strip()

            # "My name is Shanto" → "Shanto"
            name_prefixes = [
                "my name is ",
                "my name's ",
                "i am ",
                "i'm ",
                "this is ",
                "আমার নাম ",
                "আমি "
            ]

            for prefix in name_prefixes:
                if name_text.lower().startswith(prefix.lower()):
                    name_text = name_text[len(prefix):].strip()
                    break

            # শেষে punctuation থাকলে বাদ
            name_text = name_text.strip(" .,!?:;")

            user_data["name"] = name_text

            user_data["step"] = "problem"

            if language == "en":
                reply = (
                    f"Welcome {user_data['name']}. I am SasthoBondhu. "
                    "Please describe your health problem."
                )
            else:
                reply = (
                    f"স্বাগতম {user_data['name']}। "
                    "আমি স্বাস্থ্যবন্ধু। আপনার স্বাস্থ্য সমস্যাটি বলুন।"
                )

            audio_file = create_audio(reply, language)

            chat_history.append({
                "user": original_message,
                "ai": reply
            })

            return render_template(
                "index.html",
                chat_history=chat_history,
                language=language,
                audio_file=audio_file
            )

        
        if user_data["active"] and user_data["step"] == "problem":

            matched_diseases = get_disease_data_with_gemini(user_message)

            if matched_diseases:

                # সব matched disease save করছি
                user_data["problems"] = [
                    disease_key
                    for disease_key, disease_info in matched_diseases
                ]
                user_data["step"] = "location"

                reply = get_text(
                    language,
                    "ask_location",
                    name=user_data["name"]
                )

                audio_file = create_audio(reply, language)

                chat_history.append({
                    "user": original_message,
                    "ai": reply
                })

                return render_template(
                    "index.html",
                    chat_history=chat_history,
                    language=language,
                    audio_file=audio_file
                )

            else:
                if language == "en":
                    reply = """
                    I could not understand your problem.

                    Please describe your problem in another way.
                        """
                else:
                    reply = """
                    আপনার সমস্যাটি বুঝতে পারিনি।

                    একটু অন্যভাবে সমস্যাটি বলুন।
                    """

                audio_file = create_audio(reply, language)

                chat_history.append({
                    "user": original_message,
                    "ai": reply
                })

                return render_template(
                    "index.html",
                    chat_history=chat_history,
                    language=language,
                    audio_file=audio_file
                )

                        
        if user_data["active"] and user_data["step"] == "location":

            user_data["location"] = original_message
            user_data["step"] = "hospital"

            location = original_message.lower().strip()

            hospital_name = ""
            hospital_beds = ""
            hospital_data = None

            # ---------------------------------
            # SMART LOCATION EXTRACTION
            # ---------------------------------

            normalized_location = location

            # আগে বাংলা location detect
            for bangla, english in district_map.items():
                if bangla.lower() in location:
                    normalized_location = english.lower()
                    break

            # English location detect
            else:
                for hospital in hospitals:
                    district = hospital["district"].strip().lower()

                    if district in location:
                        normalized_location = district
                        break

            # =========================
            # RECORD DASHBOARD DATA
            # =========================

            dashboard_district = normalized_location.title()

            # Disease + District statistics
            for disease_key in user_data.get("problems", []):
            
                record_dashboard_report(
                    disease_key,
                    dashboard_district
                )

            # District/location থেকে hospital খোঁজা
            for hospital in hospitals:

                hospital_district = hospital["district"].strip().lower()

                if hospital_district == normalized_location:

                    hospital_name = hospital["name"]
                    hospital_beds = hospital["beds"]
                    hospital_data = hospital

                    user_data["hospital_data"] = hospital

                    break

            # ---------------- DISEASE RESPONSE ----------------

            replies = []
            hospital_needed = False

            for disease_key in user_data.get("problems", []):

                disease_info = disease_data.get(disease_key)

                if not disease_info:
                    continue

                # মূল পরামর্শ
                response = get_localized_disease_text(
                    disease_info,
                    language,
                    "response"
                )

                if response:
                    replies.append(response)


                # সম্ভাব্য কারণ
                possible_conditions = get_localized_disease_text(
                    disease_info,
                    language,
                    "possible_conditions"
                )

                if possible_conditions:

                    if language == "en":
                        replies.append(
                            "This may be caused by "
                            + ", ".join(possible_conditions)
                            + "."
                        )
                    else:
                        replies.append(
                            "এটি "
                            + ", ".join(possible_conditions)
                            + " এর কারণে হতে পারে।"
                        )


                # প্রয়োজনীয় পরীক্ষা
                tests = disease_info.get(
                    "tests",
                    []
                )

                if tests:

                    if language == "en":
                        replies.append(
                            "The doctor may recommend "
                            + ", ".join(tests)
                            + "."
                        )
                    else:
                        replies.append(
                            "ডাক্তার আপনাকে "
                            + ", ".join(tests)
                            + " দিতে পারে।"
                        )

                # Emergency হলে hospital লাগবে
                if disease_info.get("emergency", False):

                    hospital_needed = True


            # Disease response তৈরি
            reply = "\n".join(replies)


            # Emergency হলে hospital information যোগ হবে

            if hospital_name:

                ticket_info = hospital_data.get("ticket", {})

                if language == "en":
                    hospital_name_en = hospital_data.get(
                        "name_en",
                        hospital_name
                    )
                    ticket_location_en = ticket_info.get(
                        "location_en",
                        "the ticket counter"
                    )
                    ticket_price = ticket_info.get(
                        "price",
                        "N/A"
                    )
                    reply += f"""
            The nearest hospital to your location is
            {hospital_name_en}.

            Go to {ticket_location_en} and collect a ticket.
            The ticket costs {ticket_price} BDT.

            Then see the doctor.
            Be cautious if any third party at the hospital asks for money in exchange for assistance.
            """

                else:
                    ticket_location = ticket_info.get(
                        "location",
                        "তথ্য নেই"
                    )
                    ticket_price = ticket_info.get(
                        "price",
                        "তথ্য নেই"
                    )
                    reply += f"""
            আপনার জন্য নিকটস্থ হাসপাতাল {hospital_name}।

            {ticket_location} থেকে টিকেট কাটবেন।
            টিকেটের দাম {ticket_price} টাকা।

            তারপর ডাক্তার দেখান।
            হাসপাতালে কোনো তৃতীয় ব্যক্তি সাহায্যের বিনিময়ে টাকা চাইলে সতর্ক থাকবেন।
            """

            else:
                if language == "en":
                    reply += """
            This may be an emergency. Please seek medical attention without delay.

            If the condition is serious, go directly to the nearest emergency department.
            """

                else:
                    reply += """
            এটি জরুরি হতে পারে। দেরি না করে দ্রুত চিকিৎসা নিন।

            অবস্থা গুরুতর হলে সরাসরি নিকটস্থ জরুরি বিভাগে যান।
            """

            audio_file = create_audio(reply, language)
            chat_history.append({
                "user": original_message,
                "ai": reply
            })
            user_data["step"] = "post_hospital"
            return render_template(
                "index.html",
                chat_history=chat_history,
                language=language,
                audio_file=audio_file
            )




        if (
            user_data["active"]
            and user_data["step"] == "post_hospital"
        ):
            
            

            hospital_data = user_data.get("hospital_data")


            test_words = [
                "টেস্ট",
                "পরীক্ষা",
                "test",
                "tests",
                "where to do the test",
                "where can i do the test",
                "where to test",
                "investigation",
                "investigations",
                "checkup",
                "check-up"
            ]

            if any(word in original_message.lower() for word in test_words):

                if hospital_data:
                    test_data = hospital_data.get("tests", {})
                    replies = []

                    for disease_key in user_data.get("problems", []):
                        disease_info = disease_data.get(disease_key)

                        if not disease_info:
                            continue

                        required_tests = disease_info.get("tests", [])

                        for test in required_tests:

                            if test not in test_data:
                                continue

                            test_info = test_data[test]

                            test_location = test_info.get(
                                "location",
                                "তথ্য নেই"
                            )

                            test_price = test_info.get(
                                "price",
                                "তথ্য নেই"
                            )

                            if language == "en":

                                # Bangla test-location কে English-এ দেখানোর জন্য
                                if "২ তলায়, রুম ২০৫" in test_location:
                                    test_location_en = "2nd floor, Room 205"
                                elif "২ তলায়, রুম ৩০৫" in test_location:
                                    test_location_en = "2nd floor, Room 305"
                                elif "২ তলায়, ইসিজি রুম" in test_location:
                                    test_location_en = "2nd floor, ECG room"
                                elif "৩ তলায়, রুম ৩০৫" in test_location:
                                    test_location_en = "3rd floor, Room 305"
                                elif "৩ তলায়, রুম ৫০৫" in test_location:
                                 test_location_en = "3rd floor, Room 505"
                                elif "৩ তলায়, ইসিজি রুম" in test_location:
                                    test_location_en = "3rd floor, ECG room"
                                elif "১ তলায়, ল্যাবরেটরি" in test_location:
                                    test_location_en = "1st floor, Laboratory"
                                elif "১ তলায়, ইসিজি রুম" in test_location:
                                    test_location_en = "1st floor, ECG room"
                                else:
                                    test_location_en = test_info.get(
                                        "location_en",
                                        test_location
                                    )

                                replies.append(
                                    f"For {test} please go to {test_location_en} "
                                    f"(on the right side of the stairs).\n"
                                    f"The approximate cost is {test_price} BDT."
                                )

                            else:

                                replies.append(
                                    f"{test} টেস্টের জন্য {test_location} "
                                    f"(সিঁড়ির ডান পাশে) যাবেন।\n"
                                 f"এটার জন্য প্রায় {test_price} টাকা লাগবে।"
                                )

                    if replies:
                        reply = "\n\n".join(replies)
                    else:
                        if language == "en":
                            reply = "No test information was found for your condition."
                        else:
                            reply = "আপনার সমস্যার জন্য প্রয়োজনীয় টেস্টের তথ্য পাওয়া যায়নি।"

                else:
                    if language == "en":
                        reply = "Hospital test information is not available."
                    else:
                        reply = "হাসপাতালের টেস্টের তথ্য পাওয়া যায়নি।"

                user_data["step"] = "test"

            else:

                if language == "en":
                    reply = """
                    Please ask a question if you need more information.
                    """
                else:
                    reply = """
                    আপনার প্রয়োজন অনুযায়ী আরও তথ্য জানতে প্রশ্ন করুন।
                    """

            audio_file = create_audio(reply, language)

            chat_history.append({
                "user": original_message,
                "ai": reply
            })

            return render_template(
                "index.html",
                chat_history=chat_history,
                language=language,
                audio_file=audio_file
            )        
        
        
        if user_data["active"] and user_data["step"] == "test":

            message_lower = original_message.lower()

            report_words = [
                "এরপর",
                "তারপর",
                "রিপোর্ট",
                "কি করতে হবে",
                "কী করতে হবে",
                "এখন কি",
                "এখন কী",

                "what next",
                "what should i do next",
                "what do i do next",
                "what now",
                "next",
                "report",
                "after the test",
                "after test",
                "what after the test"
            ]

            if any(word in message_lower for word in report_words):

                if language == "en":
                    reply = (
                        "You will receive the report in room 202 on the 2nd floor after 3 to 4 hours.\n\n"
                        "Collect the report by showing the receipt and show it to the doctor in room 201.\n\n"
                        "Let me know what the doctor says."
                    )
                else:
                    reply = (
                        "৩ থেকে ৪ ঘন্টা পরে রিপোর্ট পাবেন ২য় তলার ২০২ নম্বর রুমে।\n\n"
                        "রিসিপ্ট দেখিয়ে রিপোর্ট সংগ্রহ করে ২০১ নম্বর রুমে চিকিৎসককে দেখাবেন।\n\n"
                        "ডাক্তার কী বলেছেন আমাকে জানাবেন।"
                    )

                user_data["step"] = "report"

            else:

                if language == "en":
                    reply = """
                        Please complete the required tests first. Once the tests are done, ask me what to do next.
                        """
                else:
                    reply = """
                        আগে প্রয়োজনীয় পরীক্ষাগুলো সম্পন্ন করুন। পরীক্ষা শেষ হলে এরপর কী করতে হবে তা জানতে আমাকে বলুন।
                        """

            audio_file = create_audio(reply, language)

            chat_history.append({
                "user": original_message,
                "ai": reply
            })
   

            return render_template(
                "index.html",
                chat_history=chat_history,
                language=language,
                audio_file=audio_file
            )

        if user_data["active"] and user_data["step"] == "report":

            message_lower = original_message.lower()

            admission_words = [
                "ভর্তি",
                "ভর্তি হব",
                "ভর্তি হতে হবে",
                "এখন কি করব",
                "এখন কী করব",
                "এরপর কি",
                "এরপর কী",

                "admission",
                "admit",
                "get admitted",
                "what next",
                "what should i do",
                "what do i do now",
                "what now",
                "next step"
            ]

            if any(word in message_lower for word in admission_words):

                if language == "en":
                    reply = (
                        "No problem, if the doctor says for admission, how much will it cost,\n\n"
                        "I will tell you how to get admitted.\n\n"
                        "There is no reason to be tense, I am always by your side."
                    )
                else:
                    reply = (
                        "কোনো সমস্যা নেই, ডাক্তার যদি ভর্তির জন্য বলে, তাহলে কত টাকা লাগবে,\n\n"
                        "কিভাবে ভর্তি হবে আমি বলে দিবো।\n\n"
                        "টেনশনের কোনো কারণ নেই, আমি সবসময় তোমার পাশে আছি।"
                    )

                user_data["step"] = "admission"

            else:

                if language == "en":
                    reply = """
                        Once you receive the report, show it to the doctor. The doctor will decide whether further treatment or admission is needed.
                        """
                else:
                    reply = """
                        রিপোর্ট পাওয়ার পর সেটি ডাক্তারকে দেখান। পরবর্তী চিকিৎসা বা হাসপাতালে ভর্তি হওয়া প্রয়োজন কি না, ডাক্তার তা নির্ধারণ করবেন।
                        """

            audio_file = create_audio(reply, language)

            chat_history.append({
                "user": original_message,
                "ai": reply
            })

            return render_template(
                "index.html",
                chat_history=chat_history,
                language=language,
                audio_file=audio_file
            )


        for local_word, normal_word in regional_words.items():

            if local_word in user_message:

                user_message = user_message.replace(
                    local_word,
                    normal_word
                )

        if user_message.strip().lower() in [
            "হ্যাঁ",
            "হ্যা",
            "yes",
            "haan",
            "ha",
            "ji"
        ]:

            import random
        
            ticket_id = "SB-" + str(
                random.randint(10000, 99999)
            )

            ticket_data["total_tickets"] += 1

            reply = f"""
         টিকিট বুক করা হয়েছে

        Ticket আইডি:
        {ticket_id}
        """
            audio_file = create_audio(reply, language)

            chat_history.append({
                "user": user_message,
                "ai": reply
            })

            return render_template(
                "index.html",
                chat_history=chat_history,
                language=language,
                audio_file=audio_file
            )


        # ---------------- DISEASE DATABASE ----------------

        hospital_needed = False
        reply = ""


        matched_diseases = get_disease_data_with_gemini(user_message)

        if matched_diseases:

            replies = []

            for disease_key, disease_info in matched_diseases:

                # সংক্ষিপ্ত মূল পরামর্শ
                response = get_localized_disease_text(
                    disease_info,
                    language,
                    "response"
                )

                if response:
                    replies.append(response)

                # Emergency হলে hospital লাগবে
                if disease_info.get("emergency", False):
                    hospital_needed = True

                

            reply = "\n".join(replies)

        else:

            reply = """
            দুঃখিত।
            এই সমস্যার জন্য এখনো ডেটা যুক্ত করা হয়নি।
            """

        
        for hospital in hospitals:

            if hospital["district"].lower() in user_message.lower():

                hospital_name = hospital["name"]

                break
        if hospital_name == "":

            hospital_name = "উপজেলা স্বাস্থ্য কমপ্লেক্স"

        if hospital_needed:

            hospital = get_hospital_by_district(user_message)

            if hospital:

                hospital_beds = hospital.get("beds", "N/A")
                ticket_info = hospital.get("ticket", {})

                if language == "en":

                    hospital_name = hospital.get(
                        "name_en",
                        hospital.get("name", "Nearest hospital")
                    )

                    ticket_location = ticket_info.get(
                        "location_en",
                        "the ticket counter"
                    )

                    ticket_price = ticket_info.get(
                        "price",
                        "N/A"
                    )

                    reply += f"""

        The nearest hospital to your location is
        {hospital_name}.

        Go to {ticket_location} and collect a ticket.
        The ticket costs {ticket_price} BDT.

        Then see the doctor.
        Be cautious if any third party at the hospital asks for money in exchange for assistance.
        """

                else:

                    hospital_name = hospital.get(
                        "name",
                        "নিকটস্থ হাসপাতাল"
                    )

                    ticket_location = ticket_info.get(
                        "location",
                        "তথ্য নেই"
                    )

                    ticket_price = ticket_info.get(
                        "price",
                        "তথ্য নেই"
                    )

                    reply += f"""

        আপনার বাসা থেকে সবচেয়ে কাছে হলো
        {hospital_name}।

        {ticket_location} থেকে টিকেট কাটবেন।
        টিকেটের দাম {ticket_price} টাকা।

        তারপর ডাক্তার দেখান।
        হাসপাতালে কোনো তৃতীয় ব্যক্তি আপনাকে সাহায্য করার বিনিময়ে টাকা চাইলে সতর্ক থাকবেন।
        """

            else:

                if language == "en":

                    reply += """

        This may be an emergency. Please seek medical attention without delay.

        If you provide your location, I can help find information about a nearby hospital.
        If the condition is serious, go directly to the nearest emergency department.
        """

                else:

                    reply += """

        এটি জরুরি হতে পারে। দেরি না করে দ্রুত চিকিৎসা নিন।

        আপনার অবস্থান জানা গেলে নিকটস্থ হাসপাতালের তথ্য দিতে পারব।
        অবস্থা গুরুতর হলে সরাসরি নিকটস্থ জরুরি বিভাগে যান।
        """


        reply = (
           reply.replace("*", "")
                .replace("#", "")
                .replace("**", "")
        )

        audio_file = create_audio(reply, language)

        chat_history.append({
            "user": original_message,
            "ai": reply
        })

        recent_chats.append({
            "message": original_message
        })

        if len(recent_chats) > 5:
            recent_chats.pop(0)

    return render_template(
        "index.html",
        reply=reply,
        chat_history=chat_history,
        audio_file=audio_file,
        language=language
    )

# =========================
# DASHBOARD HELPER FUNCTIONS
# =========================

def record_dashboard_report(disease, district):
    """
    Record one completed disease + location interaction.
    """

    if not disease:
        return

    # Disease count
    if disease not in disease_stats:
        disease_stats[disease] = 0
        disease_location_stats[disease] = {}

    disease_stats[disease] += 1
    dashboard_data["total_reports"] += 1

    # District count
    if district not in district_stats:
        district_stats[district] = 0

    district_stats[district] += 1

    # Disease + district count
    if district not in disease_location_stats[disease]:
        disease_location_stats[disease][district] = 0

    disease_location_stats[disease][district] += 1


def get_top_disease():
    if not disease_stats:
        return "No data"

    valid_diseases = {
        disease: count
        for disease, count in disease_stats.items()
        if count > 0
    }

    if not valid_diseases:
        return "No data"

    return max(valid_diseases, key=valid_diseases.get)


def get_top_district():
    valid_districts = {
        district: count
        for district, count in district_stats.items()
        if district != "Unknown" and count > 0
    }

    if not valid_districts:
        return "No data"

    return max(valid_districts, key=valid_districts.get)


def get_disease_location_rows():
    """
    Creates dashboard-friendly rows for
    disease + district statistics.
    """

    rows = []

    for disease, locations in disease_location_stats.items():

        total = disease_stats.get(disease, 0)

        if total == 0:
            continue

        if locations:
            top_location = max(
                locations,
                key=locations.get
            )
            top_location_count = locations[top_location]
        else:
            top_location = "Unknown"
            top_location_count = 0

        rows.append({
            "disease": disease,
            "total": total,
            "top_location": top_location,
            "top_location_count": top_location_count,
            "locations": locations
        })

    rows.sort(
        key=lambda x: x["total"],
        reverse=True
    )

    return rows

@app.route("/call")
def call():

    return render_template(
        "call.html"
    )


@app.route("/speech", methods=["POST"])
def speech():

    audio = request.files["audio"]

    audio.save("voice.webm")

    text = speech_to_text("voice.webm")

    print("User:", text)

    return jsonify({

        "text": text

    })


@app.route("/voice", methods=["POST"])
def voice():
    data = request.get_json()
    user_message = data.get("message", "")
    original_message = user_message

    is_noakhali = False

    # ১. আঞ্চলিক শব্দ চেকিং ও রূপান্তর
    for local_word, normal_word in regional_words.items():
        if local_word in user_message:
            user_message = user_message.replace(local_word, normal_word)
            is_noakhali = True

    # 🎯 আঞ্চলিক শব্দ পেলেই ডায়ালেক্ট নোয়াখালী সেট হবে
    if is_noakhali:
        user_data["dialect"] = "noakhali"

    district_found = False
    for bangla, english in district_map.items():
        if bangla in user_message:
            user_message += f" {english}"
            district_found = True
            break

    print("User:", user_message)
    print("Noakhali:", is_noakhali)

    # ---------------- FLOW START ----------------
    if "হ্যালো" in user_message or "স্বাস্থ্য" in user_message:
        user_data["mode"] = "flow"
        user_data["active"] = True
        user_data["step"] = "name"

        if is_noakhali:
            user_data["dialect"] = "noakhali"
        else:
            user_data["dialect"] = "normal"

        reply = "প্রিয় গ্রাহক, আপনার নাম বলুন?"

        if user_data.get("dialect") == "noakhali":
            reply = convert_to_noakhali(reply)

        audio_file = create_audio(reply)
        return jsonify({
            "reply": reply,
            "audio": audio_file
        })
    # ---------------- FLOW END ----------------

    # ---------------- STEP: NAME ----------------
    if user_data["active"] and user_data["step"] == "name":
        user_data["name"] = user_message
        user_data["step"] = "problem"

        reply = f"""স্বাগতম {user_data["name"]}। আমি স্বাস্থ্যবন্ধু। আপনার স্বাস্থ্য সমস্যাটি বলুন।"""

        if user_data.get("dialect") == "noakhali":
            reply = convert_to_noakhali(reply)

        audio_file = create_audio(reply)
        return jsonify({
            "reply": reply,
            "audio": audio_file
        })

    # ---------------- STEP: PROBLEM ----------------
    if user_data["active"] and user_data["step"] == "problem":
        user_data["problem"] = user_message
        user_data["step"] = "location"

        reply = f"""{user_data["name"]}, আপনি কোথায় থাকেন?"""

        if user_data.get("dialect") == "noakhali":
            reply = convert_to_noakhali(reply)

        audio_file = create_audio(reply)
        return jsonify({
            "reply": reply,
            "audio": audio_file
        })

    # ---------------- STEP: LOCATION ----------------
    if user_data["active"] and user_data["step"] == "location":

        user_data["location"] = user_message
        user_data["step"] = "hospital"

        # Clean location text
        clean_loc = (
            user_message    
            .lower()
            .strip()
            .replace("।", "")
            .replace(",", "")
            .replace("?", "")
        )

        print("MATCHING LOCATION =", clean_loc)

        # ---------------- HATIYA ----------------
        if any(k in clean_loc for k in [
            "হাতিয়া",
            "হাতিয়া",
            "হাতিয়াতে",
            "হাতিয়াতে",
            "hatiya"
        ]):

            reply = """ভয় পাওয়ার কিছু নেই। আপনার বর্ণনা অনুযায়ী এটি হামের মতো কোনো ভাইরাল সংক্রমণ হতে পারে। আপনাদের ভাষায় এটাকে "আম" বলে। আপনার বাসা থেকে সবচেয়ে কাছে হলো হাতিয়া উপজেলা স্বাস্থ্য কমপ্লেক্স। ঐখানে নিচতলায় ১০৩ নম্বর রুমে গিয়ে টিকেট কাটবেন। টিকেটের দাম ১০ টাকা। তারপর ১০৭ নম্বর রুমে গিয়ে ডাক্তার দেখান। ডাক্তার আপনাকে CBC এবং Blood Test দিতে পারে।"""

        # ---------------- SIDDHIRGANJ ----------------
        elif any(k in clean_loc for k in [
            "সিদ্ধিরগঞ্জ",
            "সিদ্ধিরগঞ্জে",
            "সিদ্ধিরগঞ্জের",
            "হীরাঝিল",
            "হিরাঝিল",
            "siddhirganj"
        ]):

            reply = """ভয় পাওয়ার কিছু নেই। আপনার বর্ণনা অনুযায়ী এটি হামের মতো কোনো ভাইরাল সংক্রমণ হতে পারে। আপনি যেহেতু সিদ্ধিরগঞ্জে থাকেন, আপনার বাসা থেকে সবচেয়ে কাছে হলো উপজেলা স্বাস্থ্য কমপ্লেক্স। ঐখানে নিচতলায় ১০৩ নম্বর রুমে গিয়ে টিকেট কাটবেন। টিকেটের দাম ১০ টাকা। তারপর ১০৭ নম্বর রুমে গিয়ে ডাক্তার দেখান। ডাক্তার আপনাকে CBC এবং Blood Test দিতে পারে।"""

        # ---------------- FATULLAH ----------------
        elif any(k in clean_loc for k in [
            "ফতুল্লা",
            "ফতুল্লায়",
            "ফতুল্লায়",
            "ফতুল্লাতে",
            "ফতুল্লার",
            "fatullah",
            "fatulla"
        ]):

            reply = """ভয় পাওয়ার কিছু নেই। আপনার বর্ণনা অনুযায়ী এটি হামের মতো কোনো ভাইরাল সংক্রমণ হতে পারে। আপনি যেহেতু ফতুল্লা এলাকায় থাকেন, আপনার বাসা থেকে সবচেয়ে কাছে হলো উপজেলা স্বাস্থ্য কমপ্লেক্স। ঐখানে নিচতলায় ১০৩ নম্বর রুমে গিয়ে টিকেট কাটবেন। টিকেটের দাম ১০ টাকা। তারপর ১০৭ নম্বর রুমে গিয়ে ডাক্তার দেখান। ডাক্তার আপনাকে CBC এবং Blood Test দিতে পারে।"""

        # ---------------- KANCHPUR ----------------
        elif any(k in clean_loc for k in [
            "কাঁচপুর",
            "কাচপুর",
            "কাঁচপুরে",
            "কাচপুরে",
            "কাঁচপুরের",
            "kanchpur"
        ]):

            reply = """ভয় পাওয়ার কিছু নেই। আপনার বর্ণনা অনুযায়ী এটি হামের মতো কোনো ভাইরাল সংক্রমণ হতে পারে। আপনি যেহেতু কাঁচপুর এলাকায় থাকেন, আপনার বাসা থেকে সবচেয়ে কাছে হলো উপজেলা স্বাস্থ্য কমপ্লেক্স। ঐখানে নিচতলায় ১০৩ নম্বর রুমে গিয়ে টিকেট কাটবেন। টিকেটের দাম ১০ টাকা। তারপর ১০৭ নম্বর রুমে গিয়ে ডাক্তার দেখান। ডাক্তার আপনাকে CBC এবং Blood Test দিতে পারে।"""

        # ---------------- CHANKHARPOOL ----------------
        elif any(k in clean_loc for k in [
            "চাঁনখারপুল",
            "চানখারপুল",
            "চাঁনখারপুলে",
            "চানখারপুলে",
            "চাঁনখারপুলের",
            "চানখারপুলের",
            "chankharpul",
            "chankharpool"
        ]):

            reply = """ভয় পাওয়ার কিছু নেই। আপনার বর্ণনা অনুযায়ী এটি হামের মতো কোনো ভাইরাল সংক্রমণ হতে পারে। আপনি যেহেতু চাঁনখারপুল এলাকায় থাকেন, আপনার জন্য নিকটস্থ বড় হাসপাতাল হলো ঢাকা মেডিকেল কলেজ হাসপাতাল। সেখানে গিয়ে নিচতলায় ১০৩ নম্বর রুমে গিয়ে টিকেট কাটবেন। টিকেটের দাম ১০ টাকা। তারপর ১০৭ নম্বর রুমে গিয়ে ডাক্তার দেখান। ডাক্তার আপনাকে CBC এবং Blood Test দিতে পারে।।"""

        # ---------------- UNKNOWN LOCATION ----------------
        else:

            reply = """নিকটবর্তী হাসপাতালে যোগাযোগ করুন। আরও তথ্য দিলে আমি সাহায্য করতে পারি।"""

        # Noakhali dialect conversion
        if user_data.get("dialect") == "noakhali":
            reply = convert_to_noakhali(reply)

        audio_file = create_audio(reply)

        return jsonify({
            "reply": reply,
            "audio": audio_file
        })

    # ---------------- STEP: HOSPITAL ----------------
    if user_data["active"] and user_data["step"] == "hospital":
        if "টেস্ট" in user_message:
            reply = """CBC টেস্টের জন্য ৩ তলায় সিঁড়ির ডান পাশে ৩০৫ নম্বর রুমে যাবেন। এটার জন্য প্রায় ১০০ টাকা লাগবে। Blood Test এর জন্য ৩ তলার ৫০৫ নম্বর রুমে যাবেন। এটার জন্য প্রায় ১৫০ টাকা লাগবে।"""
            user_data["step"] = "report"

            if user_data.get("dialect") == "noakhali":
                reply = convert_to_noakhali(reply)

            audio_file = create_audio(reply)
            return jsonify({
                "reply": reply,
                "audio": audio_file
            })

    # ---------------- STEP: REPORT ----------------
    if user_data["active"] and user_data["step"] == "report":
        if "টাকার" in user_message:
            reply = """তুমি ৩ থেকে ৪ ঘন্টা পরে রিপোর্ট পাবে। ২য় তলার ২০২ নম্বর রুম থেকে রিপোর্ট সংগ্রহ করবে। তারপর ২০১ নম্বর রুমে গিয়ে ডাক্তারকে রিপোর্ট দেখাবে। ডাক্তার কী বলেছে আমাকে জানিয়ো।"""
            user_data["step"] = "admission"

            if user_data.get("dialect") == "noakhali":
                reply = convert_to_noakhali(reply)

            audio_file = create_audio(reply)
            return jsonify({
                "reply": reply,
                "audio": audio_file
            })

    # ---------------- STEP: ADMISSION ----------------
    if user_data["active"] and user_data["step"] == "admission":
        if "ভর্তি" in user_message:
            reply = """কোনো সমস্যা নেই। ডাক্তার যদি ভর্তি হতে বলে, তাহলে কত টাকা লাগবে, কিভাবে ভর্তি হবে, সব আমি বলে দিবো। টেনেশনের কোনো কারণ নেই। আমি সবসময় তোমার পাশে আছি।"""

            user_data["active"] = False
            user_data["step"] = ""
            user_data["name"] = ""
            user_data["problem"] = ""
            user_data["location"] = ""

            if user_data.get("dialect") == "noakhali":
                reply = convert_to_noakhali(reply)

            audio_file = create_audio(reply)
            return jsonify({
                "reply": reply,
                "audio": audio_file
            })

    # ---------------- DISEASE DATABASE ----------------

    hospital_needed = False
    reply = ""

    matched_diseases = get_disease_data_with_gemini(user_message)

    if matched_diseases:

        replies = []

        for disease_key, disease_info in matched_diseases:

            replies.append(
                disease_info["response"]
            )

            if disease_info.get("emergency", False):
                hospital_needed = True

        reply = " ".join(replies)

    else:

        reply = """দুঃখিত। এই সমস্যার জন্য এখনো ডেটা যুক্ত করা হয়নি।"""

    if hospital_needed:

        hospital = get_hospital_by_district(user_message)

        if hospital:

            hospital_name = hospital["name"]
            hospital_beds = hospital["beds"]

            if user_data.get("language") == "en":

                reply += f"""

    This may be an emergency. Please seek medical attention without delay.

    Nearest hospital:
    {hospital_name}

    According to the available information, this hospital has around {hospital_beds} beds.

    If the condition is serious, go directly to the emergency department.
    Be cautious if anyone at the hospital asks for money in exchange for assistance.
    """

            else:

                reply += f"""

    এটি জরুরি হতে পারে। দেরি না করে দ্রুত চিকিৎসকের পরামর্শ নিন।

    নিকটস্থ হাসপাতাল:
    {hospital_name}

    তথ্য অনুযায়ী এখানে প্রায় {hospital_beds}টি বেড রয়েছে।

    অবস্থা গুরুতর হলে সরাসরি জরুরি বিভাগে যান।
    হাসপাতালে কোনো তৃতীয় ব্যক্তি সাহায্যের বিনিময়ে টাকা চাইলে সতর্ক থাকবেন।
    """

        else:

            if user_data.get("language") == "en":

                reply += """

    This may be an emergency. Please seek medical attention without delay.

    If you provide your location, I can help find information about a nearby hospital.
    If the condition is serious, go directly to the nearest emergency department.
    """

            else:

                reply += """

    এটি জরুরি হতে পারে। দেরি না করে দ্রুত চিকিৎসকের পরামর্শ নিন।

    আপনার অবস্থান জানা গেলে নিকটস্থ হাসপাতালের তথ্য দিতে পারব।
    অবস্থা গুরুতর হলে সরাসরি নিকটস্থ জরুরি বিভাগে যান।
    """

    if user_data.get("dialect") == "noakhali":
        reply = convert_to_noakhali(reply)

    audio_file = create_audio(reply)
    return jsonify({
        "reply": reply,
        "audio": audio_file
    })

@app.route("/dashboard")
def dashboard():

    top_disease = get_top_disease()
    top_district = get_top_district()

    disease_rows = get_disease_location_rows()

    return render_template(
        "dashboard.html",
        data=dashboard_data,
        disease_stats=disease_stats,
        tickets=ticket_data,
        recent_chats=recent_chats,
        top_district=top_district,
        district_stats=district_stats,
        top_disease=top_disease,
        disease_rows=disease_rows
    )

@app.route("/set-language", methods=["POST"])
def set_language():

    data = request.get_json()

    language = data.get("language", "bn")

    if language not in ["bn", "en", "fr"]:
        language = "bn"

    session["language"] = language
    user_data["language"] = language

    print("Selected language:", language)

    return jsonify({
        "success": True,
        "language": language
    })

@app.route("/language-test/<language>")
def language_test(language):
    lang = load_language(language)

    return f"""
    <h1>{lang['app_name']}</h1>
    <p>{lang['tagline']}</p>
    <p>{lang['welcome_text']}</p>
    """
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )