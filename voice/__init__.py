"""
Orion — Service voix local.

Pipeline STT → Orion (WebSocket controller) → TTS, exécuté en local.
Inspiré de github.com/Reezxy/Jarvis---Local-Voice-assistant (MIT).

Composants :
  - stt.SpeechToText      : faster-whisper (small int8 par défaut, multilingue)
  - vad.MicCapture        : webrtcvad agressivité 3, silence adaptatif
  - tts.TextToSpeech      : kokoro-onnx, voix française par défaut (ff_siwis)
  - player.SeamlessPlayer : sounddevice OutputStream zero-gap
  - wake_word.WakeWordDetector : transcription Whisper sur clips courts
  - orion_client.OrionClient   : WebSocket vers /ws/{device_id}
  - voice_service.VoiceService : orchestration du pipeline
"""
