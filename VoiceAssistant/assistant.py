import json
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import urllib.parse
import urllib.request

import pyttsx3
import speech_recognition as sr
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait


LANGUAGE = "en-IN"  # Use "ta-IN" if you want Tamil speech recognition.
SPEECH_RATE = 125
DEFAULT_LOCATION = "Walajabad, Kanchipuram, Tamil Nadu, India"
browser = None
speech_engine = None
LAST_RESPONSE = ""


def get_current_location():
    """Return the current city/region using IP-based geolocation when available."""
    try:
        with urllib.request.urlopen("https://ipinfo.io/json", timeout=6) as response:
            data = json.load(response)
        city = data.get("city") or ""
        region = data.get("region") or ""
        country = data.get("country") or ""
        timezone_name = data.get("timezone") or ""
        place_parts = [part for part in (city, region, country) if part]
        place = ", ".join(place_parts) if place_parts else DEFAULT_LOCATION
        return {"place": place, "timezone": timezone_name}
    except Exception:
        return {"place": DEFAULT_LOCATION, "timezone": "Asia/Kolkata"}


def get_current_time_text():
    """Return the current time in the detected local timezone."""
    location = get_current_location()
    tz_name = location.get("timezone") or "Asia/Kolkata"
    try:
        local_time = datetime.now(ZoneInfo(tz_name)).strftime("%I:%M %p")
    except Exception:
        local_time = datetime.now().strftime("%I:%M %p")
    return local_time, location.get("place", DEFAULT_LOCATION)


def extract_search_query(command):
    """Clean a command down to the actual search or task phrase."""
    query = command.strip()
    for phrase in (
        "please ", "can you ", "could you ", "search for ", "search ", "open ",
        "find ", "look for ", "tell me about ", "what is ", "who is ", "what do you know about ",
        "on google", "on youtube", "on youtube music", "for me"
    ):
        query = re.sub(rf"\b{re.escape(phrase.strip())}\b", "", query, flags=re.IGNORECASE).strip()
    query = re.sub(r"[?.!]+$", "", query).strip()
    query = re.sub(r"\s+", " ", query)
    return query


def speak(text):
    """Speak a message and also show it in the terminal."""
    global speech_engine, LAST_RESPONSE
    LAST_RESPONSE = text
    print(f"Assistant: {text}")
    try:
        if speech_engine is None:
            speech_engine = pyttsx3.init()
            voices = speech_engine.getProperty("voices")
            if voices:
                speech_engine.setProperty("voice", voices[0].id)
        speech_engine.setProperty("rate", SPEECH_RATE)
        speech_engine.stop()
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        for sentence in sentences or [text]:
            speech_engine.say(sentence)
            speech_engine.runAndWait()
    except Exception as error:
        print(f"Voice output unavailable: {error}")
        speech_engine = None


def show_help_menu():
    """Print and say the list of supported voice commands."""
    help_text = (
        "Here are the available commands: open browser, search Google, open YouTube, "
        "play music, ask about any topic, tell the time, tell the date, check the weather, "
        "say help, repeat, say goodbye, and ask who you are."
    )
    speak(help_text)


def get_date_info():
    """Return the current date in a friendly format."""
    today = datetime.now()
    return today.strftime("Today is %A, %B %d, %Y.")


def repeat_last_response():
    """Repeat the most recent assistant response if available."""
    if LAST_RESPONSE:
        speak(f"Repeating: {LAST_RESPONSE}")
    else:
        speak("There is no previous response to repeat yet.")


def set_voice_by_index(index):
    """Choose a system voice by index when multiple voices are available."""
    global speech_engine
    try:
        if speech_engine is None:
            speech_engine = pyttsx3.init()
        voices = speech_engine.getProperty("voices")
        if not voices:
            return "No voice options are available on this system."
        safe_index = max(0, min(index, len(voices) - 1))
        speech_engine.setProperty("voice", voices[safe_index].id)
        return f"Voice changed to {voices[safe_index].name}."
    except Exception as error:
        return f"Unable to change the voice: {error}"


def open_in_browser(url):
    """Open a URL in the Selenium Chrome window, creating it on first use."""
    global browser
    try:
        if browser is None:
            browser = webdriver.Chrome()
        browser.get(url)
    except WebDriverException:
        if browser is not None:
            try:
                browser.quit()
            except WebDriverException:
                pass
        browser = webdriver.Chrome()
        browser.get(url)


def wait_for_browser_close():
    """Pause voice listening until the Selenium browser window is closed."""
    global browser
    if browser is None:
        return
    speak("Browser is open. Voice listening is paused. Close the browser to continue.")
    while browser is not None:
        try:
            if not browser.window_handles:
                break
            time.sleep(1)
        except WebDriverException:
            break
    browser = None
    speak("Browser closed. Voice listening resumed.")


def play_first_youtube_result(query):
    """Open YouTube results and click the first video."""
    search_url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    open_in_browser(search_url)
    try:
        def find_first_video(driver):
            selectors = (
                "ytd-video-renderer a#thumbnail",
                "ytd-rich-item-renderer a#thumbnail",
                "a#video-title",
            )
            for selector in selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        return element
            return False

        first_video = WebDriverWait(browser, 15).until(find_first_video)
        browser.execute_script("arguments[0].click();", first_video)
        speak(f"Playing the first result for {query}.")
        wait_for_browser_close()
    except WebDriverException:
        speak(f"Search results for {query} are open. Please click a video to play it.")
        wait_for_browser_close()


def listen(recognizer, microphone):
    """Listen once and return the recognized text."""
    try:
        with microphone as source:
            speak("Listening. Speak now.")
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=12)
        text = recognizer.recognize_google(audio, language=LANGUAGE).lower()
        print(f"You: {text}")
        speak(f"I heard: {text}.")
        return text
    except sr.WaitTimeoutError:
        speak("I did not hear you. Please speak again.")
    except sr.UnknownValueError:
        speak("Sorry, I could not understand that.")
    except sr.RequestError:
        speak("Speech recognition needs an internet connection.")
    return ""


def get_information(topic):
    """Find and return a short answer without opening a browser."""
    normalized_topic = topic.lower()
    if "owner" in normalized_topic and "ipl" in normalized_topic:
        return None, "The Indian Premier League is operated by the Board of Control for Cricket in India, called the BCCI. It does not have one individual owner."

    search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "opensearch", "search": topic, "limit": 1, "namespace": 0, "format": "json"}
    )
    try:
        with urllib.request.urlopen(search_url, timeout=8) as response:
            search_results = json.load(response)
        titles = search_results[1]
        if not titles:
            return get_web_answer(topic)

        article_title = titles[0]
        title = urllib.parse.quote(article_title.replace(" ", "_"))
        article_url = f"https://en.wikipedia.org/wiki/{title}"
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
        with urllib.request.urlopen(summary_url, timeout=8) as response:
            data = json.load(response)
        summary = data.get("extract")
        if summary:
            sentences = re.split(r"(?<=[.!?])\s+", summary)
            return None, " ".join(sentences[:2])
        return get_web_answer(topic)
    except (urllib.error.URLError, json.JSONDecodeError, IndexError, KeyError):
        return get_web_answer(topic)


def get_web_answer(topic):
    """Use DuckDuckGo's instant-answer API when Wikipedia has no summary."""
    url = "https://api.duckduckgo.com/?" + urllib.parse.urlencode(
        {"q": topic, "format": "json", "no_html": 1, "skip_disambig": 1}
    )
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.load(response)
        answer = data.get("AbstractText") or data.get("Answer")
        if not answer:
            related_topics = data.get("RelatedTopics", [])
            for item in related_topics:
                if isinstance(item, dict) and item.get("Text"):
                    answer = item["Text"]
                    break
                if isinstance(item, dict) and item.get("Topics"):
                    for nested_item in item["Topics"]:
                        if nested_item.get("Text"):
                            answer = nested_item["Text"]
                            break
                if answer:
                    break
        if answer:
            sentences = re.split(r"(?<=[.!?])\s+", answer)
            return None, " ".join(sentences[:2])
    except (urllib.error.URLError, json.JSONDecodeError):
        pass
    return None, "The browser search is open with the available information."


def get_weather(location_name=None):
    """Return the live weather for the detected city or a sensible fallback."""
    place = (location_name or get_current_location().get("place") or DEFAULT_LOCATION).split(",")[0]
    url = "https://wttr.in/" + urllib.parse.quote(place) + "?format=j1"
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            data = json.load(response)
        current = data["current_condition"][0]
        description = current["weatherDesc"][0]["value"]
        temperature = current["temp_C"]
        return f"The weather in {place} is {description}, {temperature} degrees Celsius."
    except (urllib.error.URLError, json.JSONDecodeError, KeyError, IndexError):
        return "I could not get the live weather right now."


def answer_question(question):
    """Search the question in the browser and speak the available answer."""
    topic = clean_topic(question) or question
    search_url = "https://en.wikipedia.org/w/index.php?search=" + urllib.parse.quote_plus(topic)
    speak(f"Searching Wikipedia for {topic}.")
    open_in_browser(search_url)
    _, answer = get_information(topic)
    speak(answer)
    wait_for_browser_close()


def clean_topic(command):
    """Remove conversational filler so a search uses only the requested topic."""
    topic = command
    phrases = (
        r"please\s+", r"can you\s+", r"could you\s+", r"give (me )?some information about\s*",
        r"give (me )?information about\s*", r"information about\s*", r"tell me about\s*",
        r"say something about\s*", r"what is\s*", r"who is\s*", r"what do you know about\s*",
        r"who are\s*", r"owner of\s*", r"about\s*",
    )
    for phrase in phrases:
        topic = re.sub(phrase, "", topic, count=1).strip()
    words = topic.rstrip("?. ").split()
    cleaned_words = []
    for word in words:
        if not cleaned_words or word != cleaned_words[-1]:
            cleaned_words.append(word)
    return " ".join(cleaned_words)


def professional_response(command):
    """Give a more polished, professional answer for common small talk."""
    lowered = command.lower()
    if "how are you" in lowered:
        return "I am doing well, thank you. I am ready to assist you with your tasks and questions."
    if "hello" in lowered or "hi" in lowered:
        return "Hello. I am your professional voice assistant. How may I help you today?"
    if "thank you" in lowered:
        return "You are most welcome. I am here to help whenever you need me."
    if "good morning" in lowered:
        return "Good morning. I hope your day is going well. How can I support you today?"
    if "good evening" in lowered:
        return "Good evening. I am available to assist you with anything you need."
    return "Certainly. I can help you with searches, music, browsing, or quick information."


def play_music(command):
    """Open a YouTube Music search for a requested song or artist."""
    query = re.sub(r"\b(play|song|music|please|on|youtube)\b", "", command).strip()
    query = re.sub(r"^(a|some|the|ok)\s+", "", query).strip()
    if not query:
        speak("What song should I play?")
        query = listen(recognizer, microphone)
    if query:
        speak(f"Searching and playing {query}.")
        play_first_youtube_result(query)


def website_search(command, website):
    """Search a requested website, or open its home page when no query exists."""
    query = extract_search_query(command)
    if website == "youtube_music":
        base_url = "https://music.youtube.com/"
        search_url = base_url + "search?q=" + urllib.parse.quote_plus(query)
        name = "YouTube Music"
    elif website == "youtube":
        base_url = "https://www.youtube.com/"
        search_url = base_url + "results?search_query=" + urllib.parse.quote_plus(query)
        name = "YouTube"
    else:
        base_url = "https://www.google.com/"
        search_url = base_url + "search?q=" + urllib.parse.quote_plus(query)
        name = "Google"

    if query:
        speak(f"Searching {name} for {query}.")
        open_in_browser(search_url)
        wait_for_browser_close()
    else:
        speak(f"Opening {name}.")
        open_in_browser(base_url)
        wait_for_browser_close()


def handle_command(command):
    """Handle one spoken command. Return False when the assistant should stop."""
    if not command:
        return True

    lowered = command.lower()
    if any(word in lowered for word in ("exit", "quit", "stop", "goodbye", "bye")):
        speak("Goodbye. Have a productive day.")
        return False

    if any(word in lowered for word in ("help", "commands", "what can you do", "menu")):
        show_help_menu()
    elif lowered in ("open browser", "start browser", "launch browser"):
        speak("Opening your browser.")
        open_in_browser("about:blank")
        wait_for_browser_close()
    elif any(word in lowered for word in ("what time", "current time", "time now", "tell time")):
        current_time, place = get_current_time_text()
        speak(f"The current time in {place} is {current_time}.")
    elif any(word in lowered for word in ("what date", "today", "date today", "day is it")):
        speak(get_date_info())
    elif any(word in lowered for word in ("weather", "temperature outside")):
        speak(get_weather())
    elif any(word in lowered for word in ("who are you", "your name", "what are you")):
        speak("I am your professional virtual assistant. I can help with searches, weather, music, browsing, and daily information.")
    elif any(word in lowered for word in ("repeat", "say again", "repeat last")):
        repeat_last_response()
    elif "change voice" in lowered or "set voice" in lowered:
        try:
            if speech_engine is None:
                speech_engine = pyttsx3.init()
            voices = speech_engine.getProperty("voices")
            if voices:
                speak("I found multiple voices. Choosing the next available option.")
                response = set_voice_by_index(1)
                speak(response)
            else:
                speak("Only one voice is available on this system.")
        except Exception as error:
            speak(f"Voice settings could not be changed: {error}")
    elif "youtube music" in lowered and "play" not in lowered:
        website_search(command, "youtube_music")
    elif any(word in lowered for word in ("play", "song", "music")):
        play_music(command)
    elif "youtube" in lowered:
        website_search(command, "youtube")
    elif "google" in lowered:
        website_search(command, "google")
    elif (
        "information" in lowered
        or "about" in lowered
        or "tell me" in lowered
        or "who is" in lowered
        or "who are" in lowered
        or "what is" in lowered
        or "owner of" in lowered
    ):
        topic = clean_topic(command)
        if not topic:
            speak("Which topic would you like me to research?")
            topic = listen(recognizer, microphone)
        if topic:
            answer_question(topic)
    elif any(word in lowered for word in ("how are you", "hello", "hi", "good morning", "good evening", "thank you")):
        speak(professional_response(command))
    else:
        answer_question(command)
    return True


def welcome_user():
    """Give a polished local greeting using the detected date and place."""
    location = get_current_location()
    current_time, place = get_current_time_text()
    speak("Hello. I am your professional virtual assistant.")
    speak(f"The current time in {place} is {current_time}.")
    speak(get_weather(place))
    speak(get_date_info())
    speak("Say help anytime to see the command list.")
    speak("How may I assist you today?")
    listen(recognizer, microphone)
    speak("I am ready to help with searches, music, browsing, and general information.")


recognizer = sr.Recognizer()
microphone = sr.Microphone()

welcome_user()
with microphone as source:
    speak("Calibrating microphone. Please wait.")
    recognizer.adjust_for_ambient_noise(source, duration=1)

while True:
    command = listen(recognizer, microphone)
    if not handle_command(command):
        break