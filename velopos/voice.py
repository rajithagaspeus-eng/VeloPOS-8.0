"""Voice output (Windows System.Speech, OFFLINE) and voice input (SpeechRecognition, ONLINE, optional).

Security: the text to speak NEVER enters the PowerShell command line. It travels in the environment variables
VP_TEXT / VP_LANG and the script below is a constant string.

Honest limits:
* Output needs a Windows voice for the language. English is normally present. Tamil, Hindi, Arabic and Spanish
  voices exist as optional Windows speech packs (Settings -> Time & language -> Speech -> Add voices); a Sinhala
  voice for System.Speech may not exist on your Windows at all. Use 'Check installed voices' to see the truth for THIS PC.
  If no voice exists for the language the assistant stays silent (it never reads Sinhala/Tamil text with an English voice).
* Input sends the recorded audio to Google's free web speech service (internet needed, not private) and requires
  'pip install SpeechRecognition pyaudio'. It is OFF by default.
"""
import os
import re
import subprocess
import threading

IS_WINDOWS = os.name == "nt"
STT_CODE = {"en": "en-US", "si": "si-LK", "ta": "ta-IN", "hi": "hi-IN", "ar": "ar-SA", "es": "es-ES"}
MAX_CHARS = 600

SPEAK_SCRIPT = (
    "Add-Type -AssemblyName System.Speech;"
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "$v = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.TwoLetterISOLanguageName -eq $env:VP_LANG } | Select-Object -First 1;"
    "if (-not $v) { exit 3 };"
    "$s.SelectVoice($v.VoiceInfo.Name);"
    "$s.Speak($env:VP_TEXT)"
)
LIST_SCRIPT = (
    "Add-Type -AssemblyName System.Speech;"
    "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | Where-Object { $_.Enabled } | "
    "ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }"
)


def clean_for_speech(text):
    t = re.sub(r"[#*_`=•\-]{2,}", " ", str(text))
    t = re.sub(r"^[\-\u2022]\s*", "", t, flags=re.M)
    t = re.sub(r"[\x00-\x08\x0b-\x1f]", " ", t)
    return " ".join(t.split())[:MAX_CHARS]


def build_speak_job(text, lang):
    """-> (command list, environment). The command contains NO user text."""
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", SPEAK_SCRIPT]
    env = dict(os.environ, VP_TEXT=clean_for_speech(text), VP_LANG=str(lang)[:5])
    return cmd, env


def speak(text, lang="en", enabled=True, on_result=None, sync=False):
    """Speak in a background thread. on_result('ok' | 'novoice' | 'error') is called when it finishes."""
    if not enabled or not text or not IS_WINDOWS:
        return None

    def run():
        status = "error"
        try:
            cmd, env = build_speak_job(text, lang)
            r = subprocess.run(cmd, env=env, creationflags=0x08000000, timeout=45, capture_output=True)
            status = "ok" if r.returncode == 0 else ("novoice" if r.returncode == 3 else "error")
        except Exception:
            status = "error"
        if on_result:
            on_result(status)
    if sync:
        run()
        return None
    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def parse_voices(raw):
    """'Microsoft David Desktop|en-US' lines -> {'en': ['Microsoft David Desktop'], ...}"""
    out = {}
    for line in str(raw).splitlines():
        name, _, culture = line.strip().partition("|")
        if name and culture:
            out.setdefault(culture.split("-")[0].lower(), []).append(name)
    return out


def installed_voices():
    """-> (ok, {lang: [voice names]} or error text). Windows only; takes about a second."""
    if not IS_WINDOWS:
        return False, "Voice output works on Windows only."
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", LIST_SCRIPT], capture_output=True, text=True,
                           creationflags=0x08000000, timeout=40)
        if r.returncode != 0:
            return False, (r.stderr or "PowerShell failed").strip()
        return True, parse_voices(r.stdout)
    except Exception as e:
        return False, str(e)


# ------------------------------------------------------------------ voice INPUT (optional, online)
def stt_available():
    """-> (ok, message)"""
    try:
        import speech_recognition as sr
        sr.Microphone.list_microphone_names()           # raises if PyAudio is missing
    except ImportError:
        return False, "Voice input needs:  pip install SpeechRecognition pyaudio"
    except Exception as e:
        return False, f"No usable microphone / PyAudio problem: {e}"
    return True, "OK"


def listen_once(lang="en", timeout=6, phrase_limit=10):
    """Record one phrase and return the recognised text. Raises RuntimeError with a friendly message."""
    try:
        import speech_recognition as sr
    except ImportError:
        raise RuntimeError("Voice input needs:  pip install SpeechRecognition pyaudio")
    rec = sr.Recognizer()
    try:
        with sr.Microphone() as src:
            rec.adjust_for_ambient_noise(src, duration=0.4)
            audio = rec.listen(src, timeout=timeout, phrase_time_limit=phrase_limit)
        return rec.recognize_google(audio, language=STT_CODE.get(lang, "en-US"))
    except sr.WaitTimeoutError:
        raise RuntimeError("I did not hear anything. Try again.")
    except sr.UnknownValueError:
        raise RuntimeError("I could not understand the audio.")
    except sr.RequestError:
        raise RuntimeError("The online speech service is not reachable. Check the internet connection.")
    except OSError as e:
        raise RuntimeError(f"Microphone problem: {e}")
