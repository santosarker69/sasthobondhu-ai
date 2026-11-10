from flask import Flask, render_template, request, jsonify, session
import json
from google.genai import types
from gtts import gTTS
import speech_recognition as sr
from pydub import AudioSegment
import os
from dotenv import load_dotenv
import re
from i18n import (
    SUPPORTED_LANGUAGES, SHOW_DEMO_NOTE, norm_lang, m,
    GREETING_WORDS, BANGLA_GREETINGS, NAME_PREFIXES, TEST_WORDS,
    NEXT_WORDS, ADMISSION_WORDS, YES_WORDS,
    format_price, hospital_name, ticket_location, test_location
)
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


def gemini_detect_blood_intent(user_message):
    client = get_gemini_client()

    if not client:
        return None

    prompt = f"""
    Analyze the user's message and identify whether they need blood.

    Return JSON only:
    {{
        "needs_blood": true or false,
        "blood_group": "A+" or "A-" or "B+" or "B-" or
                       "AB+" or "AB-" or "O+" or "O-" or null
    }}

    Rules:
    - Understand both Bangla and English.
    - Understand indirect expressions of needing blood.
    - Do not assume a blood group if it is not mentioned.
    - Do not classify general questions about blood as blood requests.

    User message: {user_message}
    """

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0
            )
        )

        result = json.loads(response.text)

        if not isinstance(result, dict):
            return None

        return result

    except Exception as e:
        print("Blood intent detection failed:", e)
        return None


# =====================================================================
# GEMINI TURN INTERPRETER  (used by the home "/" route only)
# Gemini only UNDERSTANDS the user's message. It never writes a reply.
# All reply text still comes from our own templates / JSON data.
# If Gemini is unavailable, every call returns None and home() falls
# back to the old rule-based logic.
# =====================================================================

VALID_BLOOD_GROUPS = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}

TURN_INTENTS = [
    "greeting", "give_name", "describe_problem", "blood_request",
    "give_blood_group", "give_place", "ask_test", "ask_next",
    "ask_admission", "confirm_yes", "other"
]

STEP_HINTS = {
    "": "The conversation has not started yet.",
    "name": "The assistant just asked the user for their name.",
    "problem": "The assistant just asked the user to describe their health problem.",
    "blood_group": "The assistant just asked which blood group is needed.",
    "blood_location": "The assistant just asked in which area/location the blood is needed.",
    "location": "The assistant just asked where the user lives (area or district).",
    "post_hospital": "The assistant just gave hospital and ticket information. The user may ask about tests.",
    "test": "The assistant just gave test information. The user may ask what to do after the tests or about the report.",
    "report": "The assistant just explained the report. The user may ask about admission or what to do next.",
    "admission": "The assistant just talked about admission. The user may confirm or ask something else."
}


def gemini_interpret_turn(original_message, normalized_message, step, language):
    """
    ONE Gemini call per user turn. Returns a validated dict:
      {"intent": str, "name": str|None, "disease_keys": [str],
       "blood_group": str|None, "place": str|None}
    or None if Gemini is not available / failed (caller then uses old logic).
    """
    client = get_gemini_client()
    if client is None:
        return None

    compact_db = {
        key: info.get("keywords", [])[:12]
        for key, info in disease_data.items()
    }
    places = _known_places()
    step_hint = STEP_HINTS.get(step, "The assistant is waiting for the user's next message.")

    prompt = """
You are the language-understanding layer of SasthoBondhu AI, a health navigator
that talks to a patient like a 1:1 phone call.

You ONLY understand the user's message. You NEVER write a reply, NEVER diagnose,
NEVER give medical advice.

The user may write Bangla, English, French, Indonesian (Bahasa Indonesia), or Bangla
written in English letters (Banglish). Messages may contain spelling mistakes, missing words, slang, regional
dialect, speech-to-text errors or very short fragments. Understand the MEANING
even if one or two words are wrong or missing.

Conversation state: __STEP_HINT__

Choose exactly one intent:
- greeting: only greets or calls the assistant (hi, hello, hlw, helo, halo, hai, selamat pagi, assalamu alaikum,
  হ্যালো, স্বাস্থ্যবন্ধু ...) with no health problem and no name.
- give_name: the user tells their name (also if they only type the name).
- describe_problem: the user describes any symptom or health problem.
- blood_request: the user needs blood or a blood donor (directly or indirectly).
- give_blood_group: the user only states a blood group.
- give_place: the user only states a place (area, district, city, upazila).
- ask_test: the user asks about tests / investigations / where to do tests.
- ask_next: the user says tests are done, asks about the report, or asks what to do next.
- ask_admission: the user asks about admission / being admitted / the doctor said admit.
- confirm_yes: the user agrees (yes, ha, ji, haan, ya, iya, oke, ok, thik ache ...).
- other: anything else.

Also extract (use null / empty when absent):
- name: the person's name exactly as written, without filler such as
  "my name is" / "আমার নাম" / "ami". Return null if the message is not a name.
  The name must come from ORIGINAL message, never invented.
- disease_keys: list of keys chosen ONLY from the disease database below that are
  reasonably consistent with the described symptoms. Never invent a key. [] if none.
- blood_group: one of A+, A-, B+, B-, AB+, AB-, O+, O- (understand "o positive",
  "ও পজিটিভ", "b negetive" ...). null if not stated. Never guess.
- place: if the user mentions a place, return the best match from the known places
  list below (fix spelling, translate Bangla/Banglish to the English name in the list).
  If it is clearly a place but not in the list, return it as written. null if no place.

Return JSON only, exactly in this shape:
{"intent": "...", "name": null, "disease_keys": [], "blood_group": null, "place": null}

ORIGINAL message: __ORIGINAL__
Normalized message (regional words replaced): __NORMALIZED__

Known places: __PLACES__

Disease database (key: keywords): __DB__
"""
    prompt = (
        prompt
        .replace("__STEP_HINT__", step_hint)
        .replace("__ORIGINAL__", json.dumps(original_message, ensure_ascii=False))
        .replace("__NORMALIZED__", json.dumps(normalized_message, ensure_ascii=False))
        .replace("__PLACES__", json.dumps(places, ensure_ascii=False))
        .replace("__DB__", json.dumps(compact_db, ensure_ascii=False))
    )

    try:
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0
            )
        )
        raw = json.loads(response.text)
        return _clean_interpretation(raw)

    except Exception as e:
        print("Gemini turn interpretation failed:", type(e).__name__, e)
        return None


def _clean_interpretation(raw):
    """Validate everything Gemini returned. Never trust it blindly."""
    if not isinstance(raw, dict):
        return None

    intent = raw.get("intent")
    if intent not in TURN_INTENTS:
        intent = "other"

    # name
    name = raw.get("name")
    if isinstance(name, str):
        name = name.strip(" .,!?:;\"'")
        if not name or len(name) > 40 or len(name.split()) > 4:
            name = None
    else:
        name = None

    # diseases: only real keys from disease_data.json
    keys = raw.get("disease_keys")
    if not isinstance(keys, list):
        keys = []
    keys = [k for k in keys if isinstance(k, str) and k in disease_data]

    # blood group
    blood_group = raw.get("blood_group")
    if isinstance(blood_group, str):
        blood_group = blood_group.replace(" ", "").upper()
        if blood_group not in VALID_BLOOD_GROUPS:
            blood_group = None
    else:
        blood_group = None

    # place
    place = raw.get("place")
    if isinstance(place, str):
        place = place.strip()
        if not place or len(place) > 60:
            place = None
        else:
            for known in _known_places():
                if known.lower() == place.lower():
                    place = known
                    break
    else:
        place = None

    return {
        "intent": intent,
        "name": name,
        "disease_keys": keys,
        "blood_group": blood_group,
        "place": place
    }


def resolve_diseases(interp, user_message):
    """Gemini's disease keys first; local keyword match as safety net."""
    if interp is None:
        return get_disease_data_with_gemini(user_message)

    keys = interp.get("disease_keys") or []
    if keys:
        return [(k, disease_data[k]) for k in keys]

    return get_disease_data(user_message)




# =====================================================================
# HOSPITAL / PLACE / REPLY HELPERS  (home "/" route)
# =====================================================================

def _known_places():
    """Places Gemini may return: hospital districts, their area aliases, donor areas."""
    places = set()
    for h in ALL_HOSPITALS:
        places.add(h["district"])
        for alias in h.get("aliases", []):
            places.add(alias.title())
    for d in blood_donors:
        if d.get("district"):
            places.add(d["district"])
        if d.get("area"):
            places.add(d["area"])
    return sorted(places)


def resolve_hospital(text):
    """
    Find the hospital for a typed / extracted place (Bangla or English or Indonesian).
    Works for districts, area aliases (Sanur, Kuta, Ubud ...) and donor areas.
    Returns the hospital dict or None.
    """
    if not text:
        return None

    t = str(text).lower().strip()

    # Bangla names -> English district
    english = None
    for bangla, eng in district_map.items():
        if str(bangla).strip().lower() in t:
            english = str(eng).lower()
            break

    if english:
        for h in ALL_HOSPITALS:
            if h["district"].strip().lower() == english:
                return h

    # district name or alias written in the text
    for h in ALL_HOSPITALS:
        names = [h["district"].strip().lower()]
        names += [a.strip().lower() for a in h.get("aliases", [])]
        if any(n and n in t for n in names):
            return h

    # area known from donor data (Chashara, Mirpur ...) -> its district
    for d in blood_donors:
        area = str(d.get("area", "")).strip().lower()
        if area and area in t:
            district = str(d.get("district", "")).strip().lower()
            for h in ALL_HOSPITALS:
                if h["district"].strip().lower() == district:
                    return h

    return None


def disease_answer_lines(disease_info, language):
    """Advice + possible causes + tests for ONE disease, in the patient's language."""
    lang = norm_lang(language)
    lines = []

    response = get_localized_disease_text(disease_info, lang, "response")
    if response:
        lines.append(response)

    possible = get_localized_disease_text(disease_info, lang, "possible_conditions")
    if possible:
        lines.append(m(lang, "may_be_caused", items=", ".join(possible)))

    tests = disease_info.get("tests", [])
    if tests:
        lines.append(m(lang, "doctor_may_recommend", items=", ".join(tests)))

    return lines


def hospital_info_text(hospital, language):
    text = m(
        language,
        "hospital_info",
        hospital=hospital_name(hospital, language),
        ticket_location=ticket_location(hospital, language),
        price=format_price(hospital.get("ticket", {}).get("price"), hospital, language)
    )
    if SHOW_DEMO_NOTE and hospital.get("demo"):
        text += "\n\n" + m(language, "demo_note")
    return text


def begin_blood_flow(blood_group, language):
    """Start the blood-donor flow from ANY point of the conversation."""
    user_data["mode"] = "blood"
    user_data["blood_group"] = blood_group

    if not blood_group:
        user_data["step"] = "blood_group"
        return m(language, "blood_need_group")

    user_data["step"] = "blood_location"
    return m(language, "blood_ask_location", group=blood_group)


def build_additional_problem_reply(new_keys, language):
    """Answer for a NEW disease mentioned after the first answer was given."""
    lines = []

    for disease_key in new_keys:
        disease_info = disease_data.get(disease_key)
        if disease_info:
            lines += disease_answer_lines(disease_info, language)

    hospital = user_data.get("hospital_data")
    if hospital:
        lines.append(m(language, "same_hospital_note", hospital=hospital_name(hospital, language)))

    return "\n".join(lines)


def ui_state():
    """What the front end needs to draw the journey progress bar."""
    step = user_data.get("step", "") if user_data.get("active") else ""
    return {"step": step, "blood": step.startswith("blood")}


def hospital_card(hospital, language):
    return {
        "type": "hospital",
        "name": hospital_name(hospital, language),
        "ticket_location": ticket_location(hospital, language),
        "ticket_price": format_price(hospital.get("ticket", {}).get("price"), hospital, language),
        "warning": m(language, "scam_warning"),
        "demo": bool(SHOW_DEMO_NOTE and hospital.get("demo"))
    }


def emergency_card(language):
    return {"type": "emergency", "text": m(language, "emergency_go_now")}


def render_chat(reply, original_message, language, display=None, cards=None):
    """
    Shared tail of every answer.
      reply   = full text (spoken by the audio)
      display = text shown in the chat bubble (defaults to reply)
      cards   = structured cards (hospital / tests / donors / emergency)
    The page calls "/" with fetch() and gets JSON back (no page reload).
    """
    from datetime import datetime

    audio_file = create_audio(reply, language)
    entry = {
        "user": original_message,
        "ai": reply,
        "display": display if display is not None else reply,
        "cards": cards or [],
        "audio": audio_file,
        "time": datetime.now().strftime("%H:%M")
    }
    chat_history.append(entry)

    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify({**entry, "state": ui_state()})

    return render_template(
        "index.html",
        chat_history=chat_history,
        language=language,
        audio_file=audio_file
    )


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

# Indonesian demo hospitals. Kept in a separate file (not hospitals.json) so the
# /voice route, which only knows Bangladesh hospitals, is not affected.
try:
    with open("hospitals_id.json", "r", encoding="utf-8") as file:
        hospitals_id = json.load(file)
except FileNotFoundError:
    hospitals_id = []

# Everything the home "/" route can use
ALL_HOSPITALS = hospitals + hospitals_id


# =========================
# BLOOD DONOR DATABASE
# =========================

with open("data/blood_donors.json", "r", encoding="utf-8") as file:
    blood_donors = json.load(file)

# Indonesian (Bali) demo donors
try:
    with open("data/blood_donors_id.json", "r", encoding="utf-8") as file:
        blood_donors.extend(json.load(file))
except FileNotFoundError:
    pass



def search_blood_donors(blood_group, location):
    import re

    blood_group = re.sub(r"\s+", "", str(blood_group)).upper()
    location = str(location).strip().casefold()

    normalized_location = location.replace("য়", "য়")

    for bangla, english in district_map.items():
        bangla_name = str(bangla).strip().casefold().replace("য়", "য়")

        if bangla_name in normalized_location:
            normalized_location = str(english).strip().casefold()
            break

    matched_donors = []

    for donor in blood_donors:

        if not donor.get("available", False):
            continue

        if not donor.get("verified", False):
            continue

        donor_group = re.sub(
            r"\s+", "", str(donor.get("blood_group", ""))
        ).upper()

        if donor_group != blood_group:
            continue

        district = str(donor.get("district", "")).strip().casefold()
        area = str(donor.get("area", "")).strip().casefold()

        if (
            normalized_location not in district
            and normalized_location not in area
        ):
            continue

        matched_donors.append(donor)

    return matched_donors



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

    tts_language = {"en": "en", "bn": "bn", "id": "id", "fr": "en"}.get(language, "bn")

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



@app.route("/history")
def history():
    items = []
    for c in chat_history:
        items.append({
            "user": c.get("user", ""),
            "ai": c.get("ai", ""),
            "display": c.get("display", c.get("ai", "")),
            "cards": c.get("cards", []),
            "audio": c.get("audio"),
            "time": c.get("time", "")
        })
    return jsonify({
        "history": items,
        "state": ui_state(),
        "language": user_data.get("language", "bn")
    })


@app.route("/reset", methods=["POST"])
def reset_chat():
    """New chat button: forget the conversation and the patient."""
    chat_history.clear()
    user_data.update({
        "active": False, "step": "", "mode": "", "name": "",
        "location": "", "problems": [], "name_tries": 0
    })
    user_data.pop("hospital_data", None)
    return jsonify({"ok": True})


@app.route("/", methods=["GET", "POST"])
def home():
    """
    Patient conversation. Flow (user_data["step"]):
      name -> problem -> location -> post_hospital -> test -> report -> admission
      (+ blood_group -> blood_location, and new diseases / blood any time after the first answer)
    Gemini only UNDERSTANDS each message (gemini_interpret_turn). Every word the patient
    reads comes from data files or i18n.py. If Gemini is down, the old keyword rules run.
    """
    language = user_data.get("language", "bn")

    if request.method != "POST":
        return render_template(
            "index.html",
            reply="",
            chat_history=chat_history,
            audio_file=None,
            language=language
        )

    user_message = request.form["message"]

    form_language = request.form.get("language")
    if form_language in SUPPORTED_LANGUAGES:
        language = form_language
    else:
        language = session.get("language", "bn")
    session["language"] = language
    user_data["language"] = language

    print("Selected language:", language)

    # Regional (Noakhali) words -> standard Bangla
    original_message = user_message
    for local_word, normal_word in regional_words.items():
        if local_word in user_message:
            user_message = user_message.replace(local_word, normal_word)

    lower_message = user_message.lower().strip()
    active = bool(user_data.get("active"))
    step = user_data.get("step", "") if active else ""

    # ONE Gemini call per turn (None => old rule-based logic below)
    interp = gemini_interpret_turn(original_message, user_message, step, language)

    # ------------------------------------------------------------ greeting
    if interp is not None:
        is_greeting = (interp["intent"] == "greeting")
    else:
        is_greeting = (
            any(re.search(rf"\b{re.escape(w)}\b", lower_message) for w in GREETING_WORDS)
            or any(w in lower_message for w in BANGLA_GREETINGS)
        )

    if is_greeting:
        # a greeting starts a NEW patient: forget the previous one
        user_data["mode"] = "flow"
        user_data["active"] = True
        user_data["step"] = "name"
        user_data["name_tries"] = 0
        user_data["problems"] = []
        user_data["location"] = ""
        user_data.pop("hospital_data", None)
        return render_chat(m(language, "ask_name"), original_message, language)

    # ------------------------------------------------------------ name
    if active and step == "name":
        name_text = original_message.strip()

        if interp is not None:
            if interp["name"]:
                name_text = interp["name"]
            else:
                # not a name (e.g. a symptom): ask once more, then accept the text
                tries = user_data.get("name_tries", 0) + 1
                user_data["name_tries"] = tries
                if tries < 2:
                    return render_chat(m(language, "ask_name"), original_message, language)
        else:
            for prefix in NAME_PREFIXES:
                if name_text.lower().startswith(prefix.lower()):
                    name_text = name_text[len(prefix):].strip()
                    break

        name_text = name_text.strip(" .,!?:;")

        if not name_text:
            return render_chat(m(language, "ask_name"), original_message, language)

        user_data["name"] = name_text
        user_data["name_tries"] = 0
        user_data["step"] = "problem"

        return render_chat(m(language, "welcome", name=name_text), original_message, language)

    # ------------------------------------------------------------ problem
    if active and step == "problem":

        if interp is not None:
            blood_intent = {
                "needs_blood": interp["intent"] == "blood_request",
                "blood_group": interp["blood_group"]
            }
        else:
            blood_intent = gemini_detect_blood_intent(user_message)

        if blood_intent and blood_intent.get("needs_blood"):
            blood_group = blood_intent.get("blood_group")
            user_data["mode"] = "blood"
            user_data["blood_group"] = blood_group

            if not blood_group:
                user_data["step"] = "blood_group"
                reply = m(language, "blood_bleed_hint")
            else:
                user_data["step"] = "blood_location"
                reply = m(language, "blood_ask_location", group=blood_group)

            return render_chat(reply, original_message, language)

        matched_diseases = resolve_diseases(interp, user_message)

        if matched_diseases:
            user_data["problems"] = [key for key, info in matched_diseases]
            user_data["step"] = "location"

            recent_chats.append({"message": original_message})
            if len(recent_chats) > 5:
                recent_chats.pop(0)

            reply = m(language, "ask_location", name=user_data.get("name", ""))
        else:
            reply = m(language, "not_understood")

        return render_chat(reply, original_message, language)

    # ------------------------------------------------------------ blood group
    if active and step == "blood_group":

        group_match = re.search(
            r'(?<![A-Z])(AB|A|B|O)\s*([+-])(?![A-Z0-9])',
            original_message.upper()
        )
        gemini_group = interp["blood_group"] if interp is not None else None

        if gemini_group or group_match:
            if gemini_group:
                blood_group = gemini_group
            else:
                blood_group = (group_match.group(1) + group_match.group(2)).upper()

            user_data["blood_group"] = blood_group
            user_data["step"] = "blood_location"
            reply = m(language, "blood_group_ok", group=blood_group)
        else:
            reply = m(language, "blood_group_invalid")

        return render_chat(reply, original_message, language)

    # ------------------------------------------------------------ blood location + donor search
    if active and step == "blood_location":

        location = original_message.strip()
        if interp is not None and interp["place"]:
            location = interp["place"]

        blood_group = user_data.get("blood_group")
        user_data["location"] = location

        matched_donors = search_blood_donors(blood_group, location)
        lang = norm_lang(language)
        display_text = None
        cards = []

        if matched_donors:
            reply = m(language, "donors_found_header",
                      count=len(matched_donors), group=blood_group, location=location)
            display_text = reply.strip()
            donor_items = []

            for index, donor in enumerate(matched_donors, 1):
                if lang == "bn":
                    donor_name = donor.get("name_bn", donor.get("name", "অজানা"))
                else:
                    donor_name = donor.get("name", "Unknown")

                reply += m(language, "donor_line",
                           index=index, donor_name=donor_name,
                           donor_id=donor.get("id", "N/A"),
                           phone=donor.get("phone", "N/A"))
                donor_items.append({
                    "name": donor_name,
                    "id": donor.get("id", "N/A"),
                    "phone": donor.get("phone", "N/A"),
                    "group": blood_group
                })

            demo_donors = SHOW_DEMO_NOTE and any(str(d.get("id", "")).startswith("ID") for d in matched_donors)
            if demo_donors:
                reply += m(language, "donor_demo_note")

            cards.append({
                "type": "donors", "group": blood_group,
                "location": location, "items": donor_items, "demo": bool(demo_donors)
            })
        else:
            reply = m(language, "donors_none", group=blood_group, location=location)

        # back to where the patient was
        if user_data.get("hospital_data") and user_data.get("problems"):
            user_data["step"] = "post_hospital"
        else:
            user_data["step"] = "problem"
        user_data["mode"] = "flow"

        return render_chat(reply, original_message, language, display_text, cards)

    # ------------------------------------------------------------ location -> disease answer + hospital
    if active and step == "location":

        place = interp["place"] if (interp is not None and interp["place"]) else None
        hospital = resolve_hospital(place) if place else None
        if hospital is None:
            hospital = resolve_hospital(original_message)

        user_data["location"] = original_message
        if hospital:
            user_data["hospital_data"] = hospital
        else:
            user_data.pop("hospital_data", None)

        # dashboard
        stats_district = hospital["district"] if hospital else "Unknown"
        for disease_key in user_data.get("problems", []):
            record_dashboard_report(disease_key, stats_district)

        lines = []
        emergency = False
        for disease_key in user_data.get("problems", []):
            disease_info = disease_data.get(disease_key)
            if not disease_info:
                continue
            lines += disease_answer_lines(disease_info, language)
            if disease_info.get("emergency", False):
                emergency = True

        advice = "\n".join(lines)
        reply = advice
        display_text = advice
        cards = []

        if emergency:
            reply += "\n\n" + m(language, "emergency_go_now")
            cards.append(emergency_card(language))

        if hospital:
            reply += "\n\n" + hospital_info_text(hospital, language)
            cards.append(hospital_card(hospital, language))
        elif not emergency:
            no_hospital_text = m(language, "no_hospital", location=original_message.strip())
            reply += "\n\n" + no_hospital_text
            display_text += "\n\n" + no_hospital_text

        user_data["step"] = "post_hospital"
        return render_chat(reply, original_message, language, display_text, cards)

    # ------------------------------------------------------------ new topic after the first answer
    # Another disease or a blood request: keep earlier problems and answer this too.
    if (
        interp is not None
        and active
        and step in ("post_hospital", "test", "report", "admission")
    ):
        if interp["intent"] == "blood_request":
            return render_chat(
                begin_blood_flow(interp["blood_group"], language),
                original_message,
                language
            )

        known_problems = user_data.get("problems", [])
        new_keys = [k for k in interp["disease_keys"] if k not in known_problems]

        if new_keys and interp["intent"] in ("describe_problem", "other"):
            user_data["problems"] = known_problems + new_keys
            user_data["step"] = "post_hospital"

            hospital_for_stats = user_data.get("hospital_data") or {}
            stats_district = hospital_for_stats.get("district") or "Unknown"
            for disease_key in new_keys:
                record_dashboard_report(disease_key, stats_district)

            recent_chats.append({"message": original_message})
            if len(recent_chats) > 5:
                recent_chats.pop(0)

            return render_chat(
                build_additional_problem_reply(new_keys, language),
                original_message,
                language
            )

    # ------------------------------------------------------------ after hospital info: tests
    if active and step == "post_hospital":

        if interp is not None:
            wants_test = (interp["intent"] == "ask_test")
        else:
            wants_test = any(w in lower_message for w in TEST_WORDS)

        display_text = None
        cards = []

        if wants_test:
            hospital = user_data.get("hospital_data")

            if hospital:
                test_data = hospital.get("tests", {})
                replies = []
                test_items = []
                shown_tests = set()

                for disease_key in user_data.get("problems", []):
                    disease_info = disease_data.get(disease_key)
                    if not disease_info:
                        continue

                    for test in disease_info.get("tests", []):
                        if test not in test_data or test in shown_tests:
                            continue
                        shown_tests.add(test)

                        test_info = test_data[test]
                        replies.append(m(
                            language, "test_line",
                            test=test,
                            location=test_location(test_info, language),
                            price=format_price(test_info.get("price"), hospital, language)
                        ))
                        test_items.append({
                            "test": test,
                            "location": test_location(test_info, language),
                            "price": format_price(test_info.get("price"), hospital, language)
                        })

                if replies:
                    reply = "\n\n".join(replies)
                    demo_hospital = bool(SHOW_DEMO_NOTE and hospital.get("demo"))
                    if demo_hospital:
                        reply += "\n\n" + m(language, "demo_note")
                    display_text = m(language, "tests_intro")
                    cards = [{
                        "type": "tests",
                        "hospital": hospital_name(hospital, language),
                        "items": test_items,
                        "demo": demo_hospital
                    }]
                else:
                    reply = m(language, "no_test_info")
            else:
                reply = m(language, "no_hospital_test_info")

            user_data["step"] = "test"
        else:
            reply = m(language, "ask_question")

        return render_chat(reply, original_message, language, display_text, cards)

    # ------------------------------------------------------------ tests done -> report
    if active and step == "test":

        if interp is not None:
            wants_next = (interp["intent"] == "ask_next")
        else:
            wants_next = any(w in lower_message for w in NEXT_WORDS)

        if wants_next:
            reply = m(language, "report_info")
            user_data["step"] = "report"
        else:
            reply = m(language, "complete_tests_first")

        return render_chat(reply, original_message, language)

    # ------------------------------------------------------------ report -> admission
    if active and step == "report":

        if interp is not None:
            wants_admission = interp["intent"] in ("ask_admission", "ask_next")
        else:
            wants_admission = any(w in lower_message for w in ADMISSION_WORDS)

        if wants_admission:
            reply = m(language, "admission_info")
            user_data["step"] = "admission"
        else:
            reply = m(language, "show_doctor")

        return render_chat(reply, original_message, language)

    # ------------------------------------------------------------ "yes" -> ticket
    if interp is not None:
        said_yes = (interp["intent"] == "confirm_yes")
    else:
        said_yes = lower_message in YES_WORDS

    if said_yes:
        import random
        ticket_id = "SB-" + str(random.randint(10000, 99999))
        ticket_data["total_tickets"] += 1
        return render_chat(m(language, "ticket_booked", ticket_id=ticket_id), original_message, language)

    # ------------------------------------------------------------ everything else: disease database
    matched_diseases = resolve_diseases(interp, user_message)
    hospital_needed = False

    if matched_diseases:
        replies = []
        for disease_key, disease_info in matched_diseases:
            response = get_localized_disease_text(disease_info, norm_lang(language), "response")
            if response:
                replies.append(response)
            if disease_info.get("emergency", False):
                hospital_needed = True
        reply = "\n".join(replies)
    else:
        reply = m(language, "no_data")

    display_text = None
    cards = []

    if hospital_needed:
        hospital = resolve_hospital(user_message)
        display_text = reply.replace("*", "").replace("#", "")
        if hospital:
            reply += "\n\n" + hospital_info_text(hospital, language)
            cards.append(emergency_card(language))
            cards.append(hospital_card(hospital, language))
        else:
            ask_text = m(language, "emergency_ask_location")
            reply += "\n\n" + ask_text
            display_text += "\n\n" + ask_text.replace("*", "").replace("#", "")

    reply = reply.replace("*", "").replace("#", "")

    recent_chats.append({"message": original_message})
    if len(recent_chats) > 5:
        recent_chats.pop(0)

    return render_chat(reply, original_message, language, display_text, cards)


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

    if language not in SUPPORTED_LANGUAGES:
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