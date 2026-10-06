"""Simple runner to demo TTS and ASR features of speech.py"""
from speech import get_available_voices, speak, save_voice_profile, list_voice_profiles, listen_from_microphone


def main():
    print('Jarvis speech demo')
    try:
        voices = get_available_voices()
        print('Available voices:', len(voices))
        if voices:
            print('Using first voice to speak a test phrase...')
            first = voices[0]['id']
            speak('Hello. I am Jarvis. Voice demo activated.', voice_id=first)
    except Exception as e:
        print('Skipping TTS demo:', e)

    print('\nVoice profiles:', list_voice_profiles())

    # Optionally listen (if microphone available)
    try:
        print('\nListening for a short phrase (speak now)...')
        text = listen_from_microphone(timeout=4, phrase_time_limit=6)
        print('Recognized:', text)
    except Exception as e:
        print('Skipping ASR demo:', e)

if __name__ == '__main__':
    main()
