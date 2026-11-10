"""
i18n.py - all patient-facing reply text for SasthoBondhu AI (home "/" route).

Languages: bn (Bangla), en (English), id (Bahasa Indonesia).
French ("fr") only changes the UI labels; replies fall back to English.

To add or edit a sentence: change it in MSG below. Nothing else needs to change.
"""

import re

SUPPORTED_LANGUAGES = ["bn", "en", "fr", "id"]

# Set to False to hide the small "this is demo data" note under hospital answers.
SHOW_DEMO_NOTE = True


def norm_lang(language):
    """Language used for reply TEXT. fr -> en, unknown -> bn."""
    if language in ("bn", "en", "id"):
        return language
    if language == "fr":
        return "en"
    return "bn"


MSG = {
    # ---------------- conversation start ----------------
    "ask_name": {
        "bn": "প্রিয় গ্রাহক, আপনার নাম বলুন?",
        "en": "Dear user, please tell me your name?",
        "id": "Pengguna yang terhormat, silakan sebutkan nama Anda?",
    },
    "welcome": {
        "bn": "স্বাগতম {name}। আমি স্বাস্থ্যবন্ধু। আপনার স্বাস্থ্য সমস্যাটি বলুন।",
        "en": "Welcome {name}. I am SasthoBondhu. Please describe your health problem.",
        "id": "Selamat datang {name}. Saya SasthoBondhu. Silakan ceritakan masalah kesehatan Anda.",
    },
    "ask_location": {
        "bn": "{name}, আপনার সমস্যাটি নোট করা হয়েছে।\n\nআপনি কোথায় থাকেন?",
        "en": "{name}, your problem has been noted.\n\nWhere do you live?",
        "id": "{name}, masalah Anda sudah dicatat.\n\nAnda tinggal di mana?",
    },
    "not_understood": {
        "bn": "আপনার সমস্যাটি বুঝতে পারিনি।\n\nএকটু অন্যভাবে সমস্যাটি বলুন।",
        "en": "I could not understand your problem.\n\nPlease describe your problem in another way.",
        "id": "Saya belum memahami masalah Anda.\n\nSilakan jelaskan masalah Anda dengan cara lain.",
    },

    # ---------------- blood donor flow ----------------
    "blood_bleed_hint": {
        "bn": "অতিরিক্ত রক্তক্ষরণ হলে দ্রুত হাসপাতালে নিয়ে যান। রক্তের গ্রুপ বললে আমি সঠিক রক্ত দাতা খুঁজে দিতে পারি।",
        "en": "In case of excessive bleeding, take the person to the hospital immediately. If you provide the blood type, I can help find a suitable blood donor.",
        "id": "Jika terjadi pendarahan hebat, segera bawa orangnya ke rumah sakit. Jika Anda menyebutkan golongan darahnya, saya bisa membantu mencarikan pendonor darah yang cocok.",
    },
    "blood_need_group": {
        "bn": "আমি রক্তদাতা খুঁজে দিতে পারি। আপনার কোন রক্তের গ্রুপ প্রয়োজন?",
        "en": "I can help you find a blood donor. Which blood group do you need?",
        "id": "Saya bisa membantu mencarikan pendonor darah. Golongan darah apa yang Anda butuhkan?",
    },
    "blood_ask_location": {
        "bn": "অবশ্যই! আমি আপনাকে {group} রক্তের দাতা খুঁজে পেতে সাহায্য করব। রক্তটি কোন এলাকা বা লোকেশনে প্রয়োজন?",
        "en": "Sure! I will help you find {group} blood donors. Which area or location do you need the blood in?",
        "id": "Tentu! Saya akan membantu Anda mencari pendonor darah {group}. Di area atau lokasi mana darah tersebut dibutuhkan?",
    },
    "blood_group_ok": {
        "bn": "ঠিক আছে! আপনার {group} রক্ত প্রয়োজন। রক্তটি কোন এলাকায় প্রয়োজন?",
        "en": "Okay! {group} blood is needed. Which area or location do you need it in?",
        "id": "Baik! Darah {group} dibutuhkan. Di area atau lokasi mana Anda membutuhkannya?",
    },
    "blood_group_invalid": {
        "bn": "অনুগ্রহ করে সঠিক Blood Group বলুন। যেমন A+, B+, O+ অথবা AB-।",
        "en": "Please provide a valid blood group, such as A+, B+, O+ or AB-.",
        "id": "Mohon sebutkan golongan darah yang valid, misalnya A+, B+, O+ atau AB-.",
    },
    "donors_found_header": {
        "bn": "সুসংবাদ! {location} এলাকায় {group} গ্রুপের {count} জন যাচাইকৃত ও উপলব্ধ রক্তদাতা পাওয়া গেছে।\n\nরক্তদাতাগণ হলেন:\n\n",
        "en": "Good news! We found {count} verified and available {group} blood donor(s) in {location}.\n\nThe donors are:\n\n",
        "id": "Kabar baik! Kami menemukan {count} pendonor darah {group} yang terverifikasi dan tersedia di {location}.\n\nPendonornya adalah:\n\n",
    },
    "donor_line": {
        "bn": "{index}. {donor_name}, যার ডোনার আইডি হলো {donor_id}। যোগাযোগ করতে ফোন করুন {phone}।\n\n",
        "en": "{index}. {donor_name}, whose donor ID is {donor_id}. To contact, call {phone}.\n\n",
        "id": "{index}. {donor_name}, dengan ID pendonor {donor_id}. Untuk menghubungi, telepon {phone}.\n\n",
    },
    "donors_none": {
        "bn": "দুঃখিত, {location} এলাকায় বর্তমানে {group} গ্রুপের কোনো যাচাইকৃত ও উপলব্ধ রক্তদাতা পাওয়া যায়নি।\n\nআপনি আশেপাশের অন্য কোনো এলাকা দিয়ে চেষ্টা করতে পারেন অথবা হাসপাতালের ব্লাড ব্যাংকে যোগাযোগ করতে পারেন। জরুরি প্রয়োজনে চিকিৎসা নিতে দেরি করবেন না।",
        "en": "Sorry, no verified and available {group} donors were found in {location}.\n\nYou can try a nearby area or contact a hospital blood bank. Please do not delay urgent medical care.",
        "id": "Maaf, tidak ditemukan pendonor {group} yang terverifikasi dan tersedia di {location}.\n\nAnda dapat mencoba area terdekat atau menghubungi bank darah rumah sakit. Jangan menunda perawatan medis yang mendesak.",
    },
    "donor_demo_note": {
        "bn": "বিঃদ্রঃ এই রক্তদাতাদের তথ্য ডেমো ডেটা।",
        "en": "Note: these donor details are demo data.",
        "id": "Catatan: data pendonor ini adalah data demo.",
    },

    # ---------------- disease answer pieces ----------------
    "may_be_caused": {
        "bn": "এটি {items} এর কারণে হতে পারে।",
        "en": "This may be caused by {items}.",
        "id": "Ini mungkin disebabkan oleh {items}.",
    },
    "doctor_may_recommend": {
        "bn": "ডাক্তার আপনাকে {items} দিতে পারে।",
        "en": "The doctor may recommend {items}.",
        "id": "Dokter mungkin akan menyarankan {items}.",
    },
    "same_hospital_note": {
        "bn": "এই সমস্যাটিও আপনি একই হাসপাতাল, {hospital}-এ দেখাতে পারবেন। টেস্ট সম্পর্কে জানতে চাইলে আমাকে বলুন, আপনার সব সমস্যার টেস্টের তথ্য দিয়ে দেব।",
        "en": "You can show this problem at the same hospital, {hospital}. Ask me about the tests and I will tell you the tests for all your problems.",
        "id": "Masalah ini juga bisa Anda periksakan di rumah sakit yang sama, {hospital}. Tanyakan tentang tes kepada saya dan saya akan memberi tahu tes untuk semua masalah Anda.",
    },

    # ---------------- hospital ----------------
    "hospital_info": {
        "bn": "আপনার জন্য নিকটস্থ হাসপাতাল {hospital}।\n\n{ticket_location} থেকে টিকেট কাটবেন।\nটিকেটের দাম {price}।\n\nতারপর ডাক্তার দেখান।\nহাসপাতালে কোনো তৃতীয় ব্যক্তি সাহায্যের বিনিময়ে টাকা চাইলে সতর্ক থাকবেন।",
        "en": "The nearest hospital to your location is {hospital}.\n\nGo to {ticket_location} and collect a ticket.\nThe ticket costs {price}.\n\nThen see the doctor.\nBe cautious if any third party at the hospital asks for money in exchange for assistance.",
        "id": "Rumah sakit terdekat dari lokasi Anda adalah {hospital}.\n\nPergilah ke {ticket_location} untuk mengambil tiket.\nHarga tiketnya {price}.\n\nSetelah itu temui dokter.\nBerhati-hatilah jika ada pihak ketiga di rumah sakit yang meminta uang sebagai imbalan bantuan.",
    },
    "emergency_go_now": {
        "bn": "এটি জরুরি হতে পারে। দেরি না করে দ্রুত চিকিৎসা নিন।\n\nঅবস্থা গুরুতর হলে সরাসরি নিকটস্থ জরুরি বিভাগে যান।",
        "en": "This may be an emergency. Please seek medical attention without delay.\n\nIf the condition is serious, go directly to the nearest emergency department.",
        "id": "Ini mungkin darurat. Segera cari pertolongan medis tanpa menunda.\n\nJika kondisinya serius, langsung pergi ke instalasi gawat darurat terdekat.",
    },
    "emergency_ask_location": {
        "bn": "এটি জরুরি হতে পারে। দেরি না করে দ্রুত চিকিৎসা নিন।\n\nআপনার অবস্থান জানা গেলে নিকটস্থ হাসপাতালের তথ্য দিতে পারব।\nঅবস্থা গুরুতর হলে সরাসরি নিকটস্থ জরুরি বিভাগে যান।",
        "en": "This may be an emergency. Please seek medical attention without delay.\n\nIf you provide your location, I can help find information about a nearby hospital.\nIf the condition is serious, go directly to the nearest emergency department.",
        "id": "Ini mungkin darurat. Segera cari pertolongan medis tanpa menunda.\n\nJika Anda menyebutkan lokasi Anda, saya bisa membantu mencari informasi rumah sakit terdekat.\nJika kondisinya serius, langsung pergi ke instalasi gawat darurat terdekat.",
    },
    "no_hospital": {
        "bn": "দুঃখিত, {location} এর জন্য এখনো হাসপাতালের তথ্য নেই। অবস্থা খারাপ মনে হলে দেরি না করে নিকটস্থ হাসপাতালে যান।",
        "en": "Sorry, I do not have hospital information for {location} yet. If you feel worse, go to the nearest hospital without delay.",
        "id": "Maaf, saya belum memiliki informasi rumah sakit untuk {location}. Jika kondisi Anda memburuk, segera pergi ke rumah sakit terdekat.",
    },
    "scam_warning": {
        "bn": "হাসপাতালে কোনো তৃতীয় ব্যক্তি সাহায্যের বিনিময়ে টাকা চাইলে সতর্ক থাকবেন।",
        "en": "Be cautious if any third party at the hospital asks for money in exchange for assistance.",
        "id": "Berhati-hatilah jika ada pihak ketiga di rumah sakit yang meminta uang sebagai imbalan bantuan.",
    },
    "tests_intro": {
        "bn": "আপনার সমস্যার জন্য প্রয়োজনীয় টেস্টগুলো নিচে দেওয়া হলো।",
        "en": "Here are the tests for your problem(s).",
        "id": "Berikut tes yang diperlukan untuk masalah Anda.",
    },
    "price_fair": {
        "bn": "ঠিক আছে। {hospital}-এ {item} এর সঠিক দাম প্রায় {official}। আপনাকে {quoted} চাওয়া হয়েছে, এটি ন্যায্য দাম।",
        "en": "That looks fair. The real price for {item} at {hospital} is about {official}. You were asked for {quoted}, which is reasonable.",
        "id": "Harga itu wajar. Harga sebenarnya untuk {item} di {hospital} sekitar {official}. Anda diminta {quoted}, itu masih wajar.",
    },
    "price_high": {
        "bn": "দামটা একটু বেশি। {hospital}-এ {item} এর সঠিক দাম প্রায় {official}, আপনাকে {quoted} চাওয়া হয়েছে (প্রায় {times} গুণ)। সরাসরি {where}-এ গিয়ে দাম জেনে নিন।",
        "en": "That is a bit high. The real price for {item} at {hospital} is about {official}, but you were asked for {quoted} (about {times} times). Go directly to {where} and check the price yourself.",
        "id": "Harga itu agak tinggi. Harga sebenarnya untuk {item} di {hospital} sekitar {official}, tetapi Anda diminta {quoted} (sekitar {times} kali lipat). Datang langsung ke {where} dan cek harganya sendiri.",
    },
    "price_over": {
        "bn": "সতর্ক হোন! {hospital}-এ {item} এর সঠিক দাম প্রায় {official}, কিন্তু আপনাকে {quoted} চাওয়া হয়েছে, যা প্রায় {times} গুণ বেশি। দালালকে টাকা দেবেন না। সরাসরি {where}-এ গিয়ে নিজে করুন।",
        "en": "Be careful! The real price for {item} at {hospital} is about {official}, but you were asked for {quoted}, which is about {times} times higher. Do not pay the middleman. Go directly to {where} yourself.",
        "id": "Hati-hati! Harga sebenarnya untuk {item} di {hospital} sekitar {official}, tetapi Anda diminta {quoted}, sekitar {times} kali lipat. Jangan bayar ke calo. Datang langsung ke {where}.",
    },
    "price_report_ask": {
        "bn": "চাইলে এই ঘটনাটি বেনামে রিপোর্ট করতে পারেন। আপনার নাম বা ফোন নম্বর নেওয়া হবে না। রিপোর্ট করবেন? (হ্যাঁ / না)",
        "en": "If you like, you can report this anonymously. Your name and phone number are not collected. Report it? (yes / no)",
        "id": "Jika Anda mau, Anda bisa melaporkan kejadian ini secara anonim. Nama dan nomor telepon Anda tidak dikumpulkan. Laporkan? (ya / tidak)",
    },
    "price_reported": {
        "bn": "ধন্যবাদ। রিপোর্টটি বেনামে সংরক্ষণ করা হয়েছে। আপনার সতর্কতা অন্য রোগীদের সাহায্য করবে।",
        "en": "Thank you. The report was saved anonymously. Your alert will help other patients.",
        "id": "Terima kasih. Laporan disimpan secara anonim. Peringatan Anda akan membantu pasien lain.",
    },
    "price_declined": {
        "bn": "ঠিক আছে, কোনো রিপোর্ট করা হয়নি।",
        "en": "Okay, nothing was reported.",
        "id": "Baik, tidak ada yang dilaporkan.",
    },
    "price_need_info": {
        "bn": "কোন সেবার জন্য (যেমন CBC টেস্ট বা টিকেট) কত টাকা চাওয়া হয়েছে, তা বলুন।",
        "en": "Please tell me which service (for example the CBC test or the ticket) and how much money was asked.",
        "id": "Sebutkan layanan apa (misalnya tes CBC atau tiket) dan berapa uang yang diminta.",
    },
    "price_need_hospital": {
        "bn": "এটা কোন হাসপাতাল বা এলাকায়? নাম বা এলাকার নাম বলুন।",
        "en": "Which hospital or area was this? Tell me the name or the area.",
        "id": "Di rumah sakit atau area mana ini? Sebutkan nama atau daerahnya.",
    },
    "price_unknown_item": {
        "bn": "{hospital}-এর ডেটায় {item} এর দাম এখনো নেই।",
        "en": "I do not have a price for {item} at {hospital} yet.",
        "id": "Saya belum memiliki harga {item} di {hospital}.",
    },
    "demo_note": {
        "bn": "বিঃদ্রঃ এই হাসপাতালের তথ্য ডেমো ডেটা।",
        "en": "Note: this hospital information is demo data.",
        "id": "Catatan: informasi rumah sakit ini adalah data demo.",
    },

    # ---------------- tests / report / admission ----------------
    "test_line": {
        "bn": "{test} টেস্টের জন্য {location} (সিঁড়ির ডান পাশে) যাবেন।\nএটার জন্য প্রায় {price} লাগবে।",
        "en": "For {test} please go to {location} (on the right side of the stairs).\nThe approximate cost is {price}.",
        "id": "Untuk {test}, silakan menuju {location} (di sisi kanan tangga).\nPerkiraan biayanya {price}.",
    },
    "no_test_info": {
        "bn": "আপনার সমস্যার জন্য প্রয়োজনীয় টেস্টের তথ্য পাওয়া যায়নি।",
        "en": "No test information was found for your condition.",
        "id": "Informasi tes untuk kondisi Anda tidak ditemukan.",
    },
    "no_hospital_test_info": {
        "bn": "হাসপাতালের টেস্টের তথ্য পাওয়া যায়নি।",
        "en": "Hospital test information is not available.",
        "id": "Informasi tes rumah sakit tidak tersedia.",
    },
    "ask_question": {
        "bn": "আপনার প্রয়োজন অনুযায়ী আরও তথ্য জানতে প্রশ্ন করুন।",
        "en": "Please ask a question if you need more information.",
        "id": "Silakan ajukan pertanyaan jika Anda membutuhkan informasi lebih lanjut.",
    },
    "report_info": {
        "bn": "৩ থেকে ৪ ঘন্টা পরে রিপোর্ট পাবেন ২য় তলার ২০২ নম্বর রুমে।\n\nরিসিপ্ট দেখিয়ে রিপোর্ট সংগ্রহ করে ২০১ নম্বর রুমে চিকিৎসককে দেখাবেন।\n\nডাক্তার কী বলেছেন আমাকে জানাবেন।",
        "en": "You will receive the report in room 202 on the 2nd floor after 3 to 4 hours.\n\nCollect the report by showing the receipt and show it to the doctor in room 201.\n\nLet me know what the doctor says.",
        "id": "Anda akan menerima hasilnya di ruang 202 di lantai 2 setelah 3 sampai 4 jam.\n\nAmbil hasilnya dengan menunjukkan kuitansi, lalu tunjukkan kepada dokter di ruang 201.\n\nBeri tahu saya apa kata dokter.",
    },
    "complete_tests_first": {
        "bn": "আগে প্রয়োজনীয় পরীক্ষাগুলো সম্পন্ন করুন। পরীক্ষা শেষ হলে এরপর কী করতে হবে তা জানতে আমাকে বলুন।",
        "en": "Please complete the required tests first. Once the tests are done, ask me what to do next.",
        "id": "Selesaikan dulu tes yang diperlukan. Setelah tes selesai, tanyakan kepada saya apa yang harus dilakukan selanjutnya.",
    },
    "admission_info": {
        "bn": "কোনো সমস্যা নেই, ডাক্তার যদি ভর্তির জন্য বলে, তাহলে কত টাকা লাগবে,\n\nকিভাবে ভর্তি হবে আমি বলে দিবো।\n\nটেনশনের কোনো কারণ নেই, আমি সবসময় তোমার পাশে আছি।",
        "en": "No problem, if the doctor says for admission, how much will it cost,\n\nI will tell you how to get admitted.\n\nThere is no reason to be tense, I am always by your side.",
        "id": "Tidak masalah, jika dokter menyarankan rawat inap, saya akan memberi tahu berapa biayanya\n\ndan bagaimana cara mendaftar rawat inap.\n\nTidak perlu cemas, saya selalu ada di sisi Anda.",
    },
    "show_doctor": {
        "bn": "রিপোর্ট পাওয়ার পর সেটি ডাক্তারকে দেখান। পরবর্তী চিকিৎসা বা হাসপাতালে ভর্তি হওয়া প্রয়োজন কি না, ডাক্তার তা নির্ধারণ করবেন।",
        "en": "Once you receive the report, show it to the doctor. The doctor will decide whether further treatment or admission is needed.",
        "id": "Setelah menerima hasilnya, tunjukkan kepada dokter. Dokter akan memutuskan apakah diperlukan perawatan lanjutan atau rawat inap.",
    },

    # ---------------- misc ----------------
    "ticket_booked": {
        "bn": "টিকিট বুক করা হয়েছে\n\nTicket আইডি:\n{ticket_id}",
        "en": "Ticket booked\n\nTicket ID:\n{ticket_id}",
        "id": "Tiket telah dipesan\n\nID Tiket:\n{ticket_id}",
    },
    "no_data": {
        "bn": "দুঃখিত।\nএই সমস্যার জন্য এখনো ডেটা যুক্ত করা হয়নি।",
        "en": "Sorry.\nData for this problem has not been added yet.",
        "id": "Maaf.\nData untuk masalah ini belum ditambahkan.",
    },
}


def m(language, key, **kwargs):
    """Get reply text `key` in the right language, filling {placeholders}."""
    text = MSG[key][norm_lang(language)]
    return text.format(**kwargs) if kwargs else text


# ---------------------------------------------------------------------------
# Words used ONLY by the old rule-based fallback (when Gemini is unavailable)
# ---------------------------------------------------------------------------
GREETING_WORDS = [
    "hello", "hi", "hey", "sasthobondhu", "sastho bondhu", "bonjour", "salut",
    "halo", "hai", "selamat pagi", "selamat siang", "selamat sore", "selamat malam",
]
BANGLA_GREETINGS = [
    "হ্যালো", "স্বাস্থ্যবন্ধু", "স্বাস্থ্য বন্ধু",
]
NAME_PREFIXES = [
    "my name is ", "my name's ", "i am ", "i'm ", "this is ",
    "আমার নাম ", "আমি ",
    "nama saya ", "nama aku ", "saya ", "aku ",
]
TEST_WORDS = [
    "টেস্ট", "পরীক্ষা", "test", "tests", "where to do the test",
    "where can i do the test", "where to test", "investigation",
    "investigations", "checkup", "check-up",
    "tes", "pemeriksaan", "periksa", "laboratorium", "cek lab",
]
NEXT_WORDS = [
    "এরপর", "তারপর", "রিপোর্ট", "কি করতে হবে", "কী করতে হবে", "এখন কি", "এখন কী",
    "what next", "what should i do next", "what do i do next", "what now",
    "next", "report", "after the test", "after test", "what after the test",
    "selanjutnya", "setelah itu", "hasil", "laporan", "lalu apa", "apa lagi",
]
ADMISSION_WORDS = [
    "ভর্তি", "ভর্তি হব", "ভর্তি হতে হবে", "এখন কি করব", "এখন কী করব", "এরপর কি", "এরপর কী",
    "admission", "admit", "get admitted", "what next", "what should i do",
    "what do i do now", "what now", "next step",
    "rawat inap", "dirawat", "opname", "masuk rumah sakit", "selanjutnya",
]
NO_WORDS = ["না", "no", "nope", "nah", "tidak", "nggak", "gak", "enggak", "non"]
YES_WORDS = ["হ্যাঁ", "হ্যা", "yes", "haan", "ha", "ji", "ya", "iya", "oke", "ok", "baik"]


# ---------------------------------------------------------------------------
# Price / name / location helpers (work for Bangladesh AND Indonesia hospitals)
# ---------------------------------------------------------------------------

def format_price(price, hospital, language):
    lang = norm_lang(language)
    if not isinstance(price, (int, float)):
        return {"bn": "তথ্য নেই", "en": "N/A", "id": "tidak tersedia"}[lang]

    currency = (hospital or {}).get("currency", "BDT")
    if currency == "IDR":
        return "Rp " + f"{int(price):,}".replace(",", ".")
    if lang == "bn":
        return f"{price} টাকা"
    return f"{price} BDT"


def hospital_name(hospital, language):
    lang = norm_lang(language)
    if lang == "bn":
        return hospital.get("name") or hospital.get("name_en", "")
    if lang == "id":
        return hospital.get("name_id") or hospital.get("name_en") or hospital.get("name", "")
    return hospital.get("name_en") or hospital.get("name", "")


_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_TICKET_ID = {
    "Ground floor, ticket counter": "Loket tiket, lantai dasar",
}


def _ordinal_en(n):
    return {1: "1st", 2: "2nd", 3: "3rd"}.get(n, f"{n}th")


def bn_location_to(text, lang):
    """
    Convert a Bangla location like '৩ তলায়, রুম ৩০৫' to English or Indonesian.
    lang: 'en' or 'id'. Unknown formats are returned unchanged.
    """
    match = re.match(r"^\s*([০-৯]+)\s*তলায়,\s*(.+?)\s*$", text or "")
    if not match:
        return text

    floor = int(match.group(1).translate(_BN_DIGITS))
    rest = match.group(2)

    room = re.match(r"^রুম\s*([০-৯]+)$", rest)
    if room:
        number = room.group(1).translate(_BN_DIGITS)
        en_rest, id_rest = f"Room {number}", f"Ruang {number}"
    elif "ইসিজি" in rest:
        en_rest, id_rest = "ECG room", "Ruang EKG"
    elif "এক্স-রে" in rest:
        en_rest, id_rest = "X-Ray room", "Ruang Rontgen"
    elif "ল্যাবরেটরি" in rest:
        en_rest, id_rest = "Laboratory", "Laboratorium"
    else:
        en_rest = id_rest = rest

    if lang == "id":
        return f"Lantai {floor}, {id_rest}"
    return f"{_ordinal_en(floor)} floor, {en_rest}"


def ticket_location(hospital, language):
    lang = norm_lang(language)
    ticket = hospital.get("ticket", {})
    if lang == "bn":
        return ticket.get("location") or ticket.get("location_en", "তথ্য নেই")
    if lang == "id":
        if ticket.get("location_id"):
            return ticket["location_id"]
        en = ticket.get("location_en", "")
        return _TICKET_ID.get(en, en or "loket tiket")
    return ticket.get("location_en") or ticket.get("location", "the ticket counter")


def test_location(test_info, language):
    lang = norm_lang(language)
    bn = test_info.get("location", "")
    if lang == "bn":
        return bn or "তথ্য নেই"
    if lang == "id":
        return test_info.get("location_id") or bn_location_to(bn, "id")
    return test_info.get("location_en") or bn_location_to(bn, "en")


_TICKET_LABEL = {"bn": "টিকেট", "en": "ticket", "id": "tiket"}


def item_label(item, language):
    """Readable name of a priced service: 'ticket' or a test name like CBC."""
    if item == "ticket":
        return _TICKET_LABEL[norm_lang(language)]
    return item