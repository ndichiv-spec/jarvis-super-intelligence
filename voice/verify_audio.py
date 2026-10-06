"""verify_audio.py
Simple verifier for TTS/ASR dependencies and devices.
"""
import sys


def check_tts():
    try:
        import pyttsx3
        engine = pyttsx3.init()
        voices = engine.getProperty('voices')
        print(f"pyttsx3: OK — {len(voices)} voice(s) available")
        return True
    except Exception as e:
        print(f"pyttsx3: ERROR — {e}")
        return False


def check_speech_recognition():
    try:
        import speech_recognition as sr
        r = sr.Recognizer()
        print("speech_recognition: OK")
        return True
    except Exception as e:
        print(f"speech_recognition: ERROR — {e}")
        return False


def check_pyaudio():
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        count = p.get_device_count()
        print(f"pyaudio: OK — {count} device(s) detected")
        p.terminate()
        return True
    except Exception as e:
        print(f"pyaudio: ERROR — {e}")
        return False


if __name__ == '__main__':
    ok = True
    print('Running audio stack checks...')
    ok = check_tts() and ok
    ok = check_speech_recognition() and ok
    ok = check_pyaudio() and ok
    if ok:
        print('\nAll checks passed (imports and basic device listing OK).')
        sys.exit(0)
    else:
        print('\nOne or more checks failed. See messages above for details.')
        sys.exit(2)
