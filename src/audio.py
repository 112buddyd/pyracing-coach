"""Non-blocking TTS audio cues via pyttsx3."""
import threading
import pyttsx3


class AudioCoach:
    """Speaks coaching cues on a background thread using the system TTS engine.

    Cues are dropped if the engine is already speaking to avoid queuing stale callouts.
    """

    def __init__(self, rate: int, volume: float, voice_name: str = "",
                 voice_index: int = 0) -> None:
        self._engine: pyttsx3.Engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        self._engine.setProperty("volume", volume)

        voices = self._engine.getProperty("voices")
        if voices:
            # Prefer voice by name, fall back to index
            if voice_name:
                for v in voices:
                    if v.name == voice_name:
                        self._engine.setProperty("voice", v.id)
                        break
            elif 0 <= voice_index < len(voices):
                self._engine.setProperty("voice", voices[voice_index].id)

        self._lock: threading.Lock = threading.Lock()
        self._busy: bool = False

    def say(self, text: str) -> None:
        """Speak text on a background thread; drops the cue if already speaking."""
        if self._busy:
            return

        def _speak() -> None:
            with self._lock:
                self._busy = True
                try:
                    self._engine.say(text)
                    self._engine.runAndWait()
                finally:
                    self._busy = False

        threading.Thread(target=_speak, daemon=True).start()
