from flask import Flask, render_template, request, jsonify
import json
from google import genai
from gtts import gTTS
import speech_recognition as sr
from pydub import AudioSegment
import os
from dotenv import load_dotenv
load_dotenv()

chat_history = []
user_data = {
    "active": False,
    "step": "",
    "location": "",
    "name": "",
    "mode": ""
}
ticket_data = {
    "total_tickets": 0
}
dashboard_data = {
    "total_users": 0,
    "জ্বর": 0,
    "কাশি": 0,
    "মাথা ব্যথা": 0,
    "পেট ব্যথা": 0,
    "অন্যান্য": 0
}
district_stats = {
    "Dhaka": 0,
    "Narayanganj": 0,
    "Noakhali": 0,
    "Cumilla": 0,
    "Chattogram": 0,
    "Unknown": 0
}
recent_chats = []

app = Flask(__name__)

import os

client = genai.Client(
    api_key=os.environ.get("GEMINI_API_KEY")
)

with open("hospitals.json", "r") as file:
    hospitals = json.load(file)
    
district_map = {
        "ঢাকা": "Dhaka",
        "ঢাকায়": "Dhaka",
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
        "রাজশাহী": "Rajhsahi",
        "রাজশাহীতে": "Rajhsahi",
        "রাজশাহীর": "Rajhsahi",
        "সিলেট": "Sylhet",
        "সিলেটে": "Sylhet",
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
fallback_data = {
    "জ্বর": "জ্বর সাধারণ ভাইরাল সংক্রমণ বা অন্য কারণে হতে পারে। পর্যাপ্ত বিশ্রাম নিন এবং সমস্যা বাড়লে চিকিৎসকের পরামর্শ নিন।",

    "কাশি": "কাশি সাধারণ ঠান্ডা, এলার্জি বা সংক্রমণের কারণে হতে পারে। দীর্ঘস্থায়ী হলে ডাক্তারের পরামর্শ নিন।",

    "মাথা ব্যথা": "মাথা ব্যথা ক্লান্তি, ঘুমের অভাব বা অন্য কারণে হতে পারে। বিশ্রাম নিন এবং সমস্যা বাড়লে চিকিৎসকের পরামর্শ নিন।",

    "পেট ব্যথা": "পেট ব্যথা হজমজনিত সমস্যা বা অন্য কারণে হতে পারে। তীব্র হলে চিকিৎসকের পরামর্শ নিন।",

    "বুক ব্যথা": "বুক ব্যথা গুরুত্বের সাথে নিতে হবে। দ্রুত নিকটস্থ হাসপাতালে যোগাযোগ করুন।",

    "শ্বাসকষ্ট": "শ্বাসকষ্ট হলে দ্রুত চিকিৎসা নেওয়া প্রয়োজন।",

    "ডায়রিয়া": "প্রচুর পানি পান করুন এবং প্রয়োজন হলে চিকিৎসকের পরামর্শ নিন।",

    "বমি": "শরীরে পানিশূন্যতা এড়াতে পর্যাপ্ত তরল গ্রহণ করুন।",

    "গলা ব্যথা": "গলা ব্যথা সংক্রমণ বা ঠান্ডার কারণে হতে পারে।",

    "দুর্বলতা": "পর্যাপ্ত বিশ্রাম ও পুষ্টিকর খাবার গ্রহণ করুন।"
}
def convert_to_noakhali(reply):

    for normal, local in noakhali_reply_words.items():

        reply = reply.replace(normal, local)

    return reply

def create_audio(reply):

    import uuid

    audio_file = (
        f"reply_{uuid.uuid4().hex}.mp3"
    )

    tts = gTTS(
        text=reply,
        lang="bn",
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

    if request.method == "POST":

        user_message = request.form["message"]

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

        if "হ্যালো" in original_message:
            user_data["mode"] = "flow"
            user_data["active"] = True
            user_data["step"] = "name"

            reply = """ 
        প্রিয় গ্রাহক, আপনার নাম বলুন?
        """
            audio_file = create_audio(reply)

            chat_history.append({
                "user": original_message,
                "ai": reply
            })

            return render_template(
                "index.html",
                chat_history=chat_history,
                audio_file=audio_file

            )
        
        if (
           user_data["active"]
           and user_data["step"] == "name"
        ):

           user_data["name"] = original_message

           user_data["step"] = "problem"
       
           reply = f"""
        স্বাগতম {user_data["name"]}।

        আমি স্বাস্থ্যবন্ধু।

        আপনার স্বাস্থ্য সমস্যাটি বলুন।
        """

           audio_file = create_audio(reply)

           chat_history.append({
               "user": original_message,
               "ai": reply
           })

           return render_template(
               "index.html",
               chat_history=chat_history,
               audio_file=audio_file
           )

        
        if (
            user_data["active"]
            and user_data["step"] == "problem"
        ):

            if "জ্বর" in user_message:

                user_data["problem"] = "জ্বর"
                user_data["step"] = "location"

                reply = f"""
                {user_data["name"]},

                আপনি কোথায় থাকেন?
                """
                audio_file = create_audio(reply)

                chat_history.append({
                    "user": original_message,
                    "ai": reply
                })

                return render_template(
                    "index.html",
                    chat_history=chat_history,
                    audio_file=audio_file
                )
        
        if user_data["active"] and user_data["step"] == "location":
            user_data["location"] = original_message
            user_data["step"] = "hospital"

            location = original_message.lower()
           
            if "হাতিয়া" in location or "হাতিয়া" in location:
                if is_noakhali:

                    reply = f"""
                    {user_data["name"]},
                ডরানের কিছু নাই। আপনার কাথা (কথা) অনুযায়ী হিয়েন হামের মতো কোনো ভাইরাল ইনফেকশন হইতে পারে। 
                আঁরগোর এলাকায় হিয়েনরে “আম” কয়। আপনার বাসা থন হদ্দে (সবচেয়ে) কাছে হইলো উপজেলা স্বাস্থ্য কমপ্লেক্স।
                হিয়ানে যাই নিচে ১০৩ নম্বর রুম থন টিকেট কাটেন, টিকেটের দাম ১০ টেহা। হেরপর ১০৭ নম্বর রুমে যাইয়া ডাক্তার দেহান।
                ডাক্তার আপনেরে CBC, Blood Test দিতে পারে।
                """
                    audio_file = create_audio(reply)

                else:

                    reply = """
                ভয় পাওয়ার কিছু নেই।
            আপনার বর্ণনা অনুযায়ী এটি হামের মতো কোনো ভাইরাল সংক্রমণ হতে পারে। আপনাদের ভাষায় এটাকে “আম” বলে।
            আপনার বাসা থেকে সবচেয়ে কাছে হলো হাতিয়া উপজেলা স্বাস্থ্য কমপ্লেক্স। ঐখানে নিচতলায় ১০৩ নম্বর রুমে গিয়ে টিকেট কাটবেন,
            টিকেটের দাম ১০ টাকা। তারপর ১০৭ নম্বর রুমে গিয়ে ডাক্তার দেখান। ডাক্তার আপনাকে CBC,Blood টেস্ট দিতে পারে।
            """
                    audio_file = create_audio(reply)
            else:
                reply = """
            নিকটবর্তী হাসপাতালে যোগাযোগ করুন।
            আরও তথ্য দিলে আমি সাহায্য করতে পারি।
            """
                audio_file = create_audio(reply)
            chat_history.append({
               "user": original_message,
               "ai": reply
            })

            return render_template(
                "index.html",
                chat_history=chat_history,
                audio_file=audio_file

            )
        
        if user_data["active"] and "টেস্ট" in original_message:
             reply = """
        "CBC" টেস্টের জন্য ৩ তলায় সিঁড়ির ডান পাশে ৩০৫ নম্বর রুমে এ যাবেন। এটার জন্য ১০০ টাকার মতো লাগবে।
        "Blood Test" এর জন্য আপনি যাবেন ৩ তোলার ৫০৫ নম্বর রুমে। এই টেস্টার জন্য লাগবে ১৫০ টাকার মতো।
        """
             audio_file = create_audio(reply)

             user_data["step"] = "report"

             chat_history.append({
            "user": original_message,
            "ai": reply
        })

             return render_template(
            "index.html",
            chat_history=chat_history,
            audio_file=audio_file

        )
        if user_data["active"] and "টাকার" in original_message:
            reply = """
        তুমি ৩ থেকে  ৪ ঘন্টা পরে রিপোর্ট পাবে ২য় তোলার ২০২ নম্বর রুমে।
        রিসিপ্ট দেখিয়ে রিপোর্ট কলেক্ট করে ২০১ নম্বর রুমে ডাক্তার কে দেখাও।
        ডাক্তার কি বলেছে আমাকে জানিয়েও
        """
            audio_file = create_audio(reply)

            user_data["step"] = "admission"
            chat_history.append({
            "user": original_message,
            "ai": reply
        })

            return render_template(
            "index.html",
            chat_history=chat_history,
            audio_file=audio_file
        )
        if user_data["active"] and "ভর্তি" in original_message:
            reply = """কোনো সমস্যা নেই, ডাক্তার যদি ভর্তির জন্য বলে, তাহলে কত টাকা লাগবে,
         কিভাবে ভর্তি হবে আমি বলে দিবো।
        টেনশনের কোনো কারণ নেই, আমি সবসময় তোমার পাশে আছি।
        """
            audio_file = create_audio(reply)

            user_data["active"] = False
            user_data["step"] = ""
            user_data["name"] = ""
            chat_history.append({
            "user": original_message,
            "ai": reply
        })

            return render_template(
            "index.html",
            chat_history=chat_history,
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
            audio_file = create_audio(reply)

            chat_history.append({
                "user": user_message,
                "ai": reply
            })

            return render_template(
                "index.html",
                chat_history=chat_history,
                audio_file=audio_file
            )
        
        dashboard_data["total_users"] += 1

        if "জ্বর" in user_message:
            dashboard_data["জ্বর"] += 1

        elif "কাশি" in user_message:
            dashboard_data["কাশি"] += 1

        elif "মাথা ব্যথা" in user_message:
            dashboard_data["মাথা ব্যথা"] += 1

        elif "পেট ব্যথা" in user_message:
            dashboard_data["পেট ব্যথা"] += 1

        else:
            dashboard_data["অন্যান্য"] += 1
        
        district_found = False
        for bangla, english in district_map.items():

            if bangla in user_message:

               user_message += f" {english}"
               district_stats[english] += 1
               district_found = True
               break
        if not district_found:

            district_stats["Unknown"] += 1



        prompt = f"""
        তুমি "স্বাস্থ্যবন্ধু AI"।

        নিয়ম:

        ১. তুমি ডাক্তার নও।

        ২. কখনো রোগ নিশ্চিতভাবে নির্ণয় করবে না।

        ৩. সর্বোচ্চ ৫-৬ লাইনের মধ্যে উত্তর দিবে।

        ৪. উত্তর সংক্ষিপ্ত রাখবে।

        ৫. অপ্রয়োজনীয় ব্যাখ্যা দিবে না।

        ৬. তালিকা ব্যবহার করবে না।

        ৭. bold, markdown, *, # ব্যবহার করবে না।

        ৮. রোগ সম্পর্কে সম্ভাব্য ধারণা দিবে।

        ৯. প্রয়োজন হলে ডাক্তার বা হাসপাতালে যাওয়ার পরামর্শ দিবে।

        ১০. রোগীকে বন্ধুত্বপূর্ণ ও সহানুভূতিশীল ভাষায় উত্তর দিবে।

        ১১. সহজ বাংলা ব্যবহার করবে।

        ১২. রোগীর ভয় বাড়ায় এমন কথা বলবে না।

        ১৩. সম্ভাব্য কারণ, প্রাথমিক পরামর্শ এবং কখন ডাক্তার দেখানো উচিত তা সংক্ষেপে বলবে।

        User Message:
        {user_message}
        """


        reply = ""

        for symptom, answer in fallback_data.items():

            if symptom in user_message:

                reply = answer

                if is_noakhali:

                    reply = (
                        "ডরাইয়েন না। "
                        + reply
                    )

                break

        if reply == "":

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

        if hospital_name and "সার্ভার বর্তমানে ব্যস্ত" not in reply:

            reply += f"""

         আপনার বাসা থেকে সবচেয়ে কাছে হলো
        {hospital_name}
        ঐখানে নিচতলায় ২০৫ নম্বর রুমে গিয়ে টিকেট কাটবেন, টিকেটের দাম ৫ টাকা। তারপর ১০৭ নম্বর রুমে গিয়ে ডাক্তার দেখান।
        হাসপাতালে কোনো ৩য় ব্যক্তি আপনাকে সাহায্য করার বিনিময়ে টাকা চাইলে সতর্ক থাকবেন। 
        """
            
        reply = (
            reply.replace("*", "")
                 .replace("#", "")
                 .replace("**", "")
        )
        audio_file = create_audio(reply)
        chat_history.append(
            {
                "user": original_message,
                "ai": reply
            }
        )
        recent_chats.append(
            {
                "message": original_message
            }
        )

        if len(recent_chats) > 5:
            recent_chats.pop(0)

    return render_template(
        "index.html",
        reply=reply,
        chat_history=chat_history,
        audio_file=audio_file
    )

def get_top_disease():

    disease_data = {

        "জ্বর": dashboard_data["জ্বর"],
        "কাশি": dashboard_data["কাশি"],
        "মাথা ব্যথা": dashboard_data["মাথা ব্যথা"],
        "পেট ব্যথা": dashboard_data["পেট ব্যথা"]

    }

    top_disease = max(
        disease_data,
        key=disease_data.get
    )

    return top_disease

def get_top_district():

    return max(
        district_stats,
        key=district_stats.get
    )
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
            user_message = user_message.replace(
                local_word,
                normal_word
            )
            is_noakhali = True

    # 🎯 মূল ফিক্স: কথা বলার যেকোনো ধাপে নোয়াখালী শব্দ পাওয়া গেলেই ডায়ালেক্ট 'noakhali' হয়ে যাবে
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
    if (
        "হ্যালো" in user_message
        or
        "স্বাস্থ্য" in user_message
    ):
        user_data["mode"] = "flow"
        user_data["active"] = True
        user_data["step"] = "name"
        
        # শুরুতে নোয়াখালী বললে নোয়াখালী, প্রমিত বললে নরমাল সেট হবে
        if is_noakhali:
            user_data["dialect"] = "noakhali"
        else:
            user_data["dialect"] = "normal"

        reply = "প্রিয় গ্রাহক, আপনার নাম বলুন?"

        # যদি শুরুতেই নোয়াখালী বলে থাকে
        if user_data.get("dialect") == "noakhali":
            reply = convert_to_noakhali(reply)

        audio_file = create_audio(reply)
        return jsonify({
            "reply": reply,
            "audio": audio_file
        })
    # ---------------- FLOW END ----------------

    if (
        user_data["active"]
        and
        user_data["step"] == "name"
    ):
        user_data["name"] = user_message
        user_data["step"] = "problem"

        reply = f"""স্বাগতম {user_data["name"]}। আমি স্বাস্থ্যবন্ধু। আপনার স্বাস্থ্য সমস্যাটি বলুন।"""
        
        print(user_data)
        if user_data.get("dialect") == "noakhali":
            print("CONVERTING")
            reply = convert_to_noakhali(reply)
            print(reply)

        audio_file = create_audio(reply)
        return jsonify({
            "reply": reply,
            "audio": audio_file
        })

    if (
        user_data["active"]
        and
        user_data["step"] == "problem"
    ):
        if "জ্বর" in user_message:
            user_data["problem"] = "জ্বর"
            user_data["step"] = "location"

            reply = f"""{user_data["name"]}, আপনি কোথায় থাকেন?"""
            
            if user_data.get("dialect") == "noakhali":
                reply = convert_to_noakhali(reply)

            audio_file = create_audio(reply)
            return jsonify({
                "reply": reply,
                "audio": audio_file
            })

    if (
        user_data["active"]
        and
        user_data["step"] == "location"
    ):
        user_data["location"] = user_message
        user_data["step"] = "hospital"
        location = user_message.lower()

        if "হাতিয়া" in location or "হাতিয়া" in location:
            reply = """ভয় পাওয়ার কিছু নেই। আপনার বর্ণনা অনুযায়ী এটি হামের মতো কোনো ভাইরাল সংক্রমণ হতে পারে। আপনাদের ভাষায় এটাকে "আম" বলে। আপনার বাসা থেকে সবচেয়ে কাছে হলো উপজেলা স্বাস্থ্য কমপ্লেক্স। ঐখানে নিচতলায় ১০৩ নম্বর রুমে গিয়ে টিকেট কাটবেন। টিকেটের দাম ১০ টাকা। তারপর ১০৭ নম্বর রুমে গিয়ে ডাক্তার দেখান। ডাক্তার আপনাকে CBC এবং Blood Test দিতে পারে।"""
        else:
            reply = """নিকটবর্তী হাসপাতালে যোগাযোগ করুন। আরও তথ্য দিলে আমি সাহায্য করতে পারি।"""

        if user_data.get("dialect") == "noakhali":
            reply = convert_to_noakhali(reply)
            
        audio_file = create_audio(reply)
        return jsonify({
            "reply": reply,
            "audio": audio_file
        })
    
    if (
        user_data["active"]
        and
        user_data["step"] == "hospital"
    ):
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
    
    if (
        user_data["active"]
        and
        user_data["step"] == "report"
    ):
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
    
    if (
        user_data["active"]
        and
        user_data["step"] == "admission"
    ):
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

    # ---------------- FALLBACK ----------------
    hospital_needed = False
    reply = ""

    for symptom, answer in fallback_data.items():
        if symptom in user_message:
            reply = answer
            hospital_needed = True
            break

    if reply == "":
        reply = """দুঃখিত। এই সমস্যার জন্য এখনো ডেটা যুক্ত করা হয়নি।"""

    if hospital_needed:
        hospital_name = ""
        for hospital in hospitals:
            if hospital["district"].lower() in user_message.lower():
                hospital_name = hospital["name"]
                break

        if hospital_name == "":
            hospital_name = "উপজেলা স্বাস্থ্য কমপ্লেক্স"

        reply += f"""আপনার বাসা থেকে সবচেয়ে কাছে হলো {hospital_name}। ঐখানে নিচতলায় ২০৫ নম্বর রুমে গিয়ে টিকেট কাটবেন। টিকেটের দাম ৫ টাকা। তারপর ১০৭ নম্বর রুমে গিয়ে ডাক্তার দেখান। হাসপাতালে কোনো ৩য় ব্যক্তি আপনাকে সাহায্য করার বিনিময়ে টাকা চাইলে সতর্ক থাকবেন।"""

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

    return render_template(
        "dashboard.html",
        data=dashboard_data,
        tickets=ticket_data,
        recent_chats=recent_chats,
        top_district=top_district,
        district_stats=district_stats,
        top_disease=top_disease
    )
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )