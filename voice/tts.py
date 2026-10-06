import pyttsx3

_engine = None

def init_tts(rate: int = 150, volume: float = 1.0):
    global _engine
    if _engine is None:
        _engine = pyttsx3.init()
        _engine.setProperty('rate', rate)
        _engine.setProperty('volume', volume)
    return _engine


def speak(text: str):
    engine = init_tts()
    engine.say(text)
    engine.runAndWait()
