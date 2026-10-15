import { useState, useRef, useCallback, useEffect } from "react";
import { api } from "../services/api";

export function useVoiceRecognition() {
  const [isSupported] = useState(() => {
    return (
      typeof window !== "undefined" &&
      typeof navigator !== "undefined" &&
      Boolean(navigator.mediaDevices && window.MediaRecorder)
    );
  });

  const [isListening, setIsListening] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [error, setError] = useState(null);
  const [transcriptionMeta, setTranscriptionMeta] = useState(null);
  const [hasDetectedSpeech, setHasDetectedSpeech] = useState(false);

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const isCancelledRef = useRef(false);
  const isTranscribingRef = useRef(false);

  // Web Audio API for Voice Activity / Silence Detection
  const audioContextRef = useRef(null);
  const analyserRef = useRef(null);
  const silenceRafRef = useRef(null);
  const hasSpokenRef = useRef(false);
  const lastSpeechTimeRef = useRef(Date.now());

  // Formats elapsed seconds to "0:05" or "1:23"
  const formatTime = (secs) => {
    const mins = Math.floor(secs / 60);
    const remainder = secs % 60;
    return `${mins}:${remainder < 10 ? "0" : ""}${remainder}`;
  };

  const cleanupAudioNodes = useCallback(() => {
    if (silenceRafRef.current) {
      cancelAnimationFrame(silenceRafRef.current);
      silenceRafRef.current = null;
    }
    if (audioContextRef.current) {
      try {
        if (audioContextRef.current.state !== "closed") {
          audioContextRef.current.close().catch(() => {});
        }
      } catch {
        // ignore
      }
      audioContextRef.current = null;
      analyserRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupAudioNodes();
      if (timerRef.current) clearInterval(timerRef.current);
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        try {
          mediaRecorderRef.current.stop();
        } catch {
          // ignore
        }
      }
    };
  }, [cleanupAudioNodes]);

  // Determine best supported audio MIME type
  const getSupportedMimeType = () => {
    if (typeof MediaRecorder === "undefined") return "audio/webm";
    const types = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
      "audio/wav",
    ];
    for (const t of types) {
      if (MediaRecorder.isTypeSupported(t)) {
        return t;
      }
    }
    return "";
  };

  const stopListening = useCallback(() => {
    cleanupAudioNodes();
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
  }, [cleanupAudioNodes]);

  const startListening = useCallback(async (options = {}) => {
    const { autoStopOnSilence = false, silenceDuration = 1800 } = options;

    // Prevent overlapping capture sessions
    if (isTranscribingRef.current) return;

    setError(null);
    setTranscript("");
    setInterimTranscript("");
    isCancelledRef.current = false;
    audioChunksRef.current = [];
    setRecordingSeconds(0);
    hasSpokenRef.current = false;
    setHasDetectedSpeech(false);
    lastSpeechTimeRef.current = Date.now();

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError("Audio recording is not supported in this browser environment.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // Setup Web Audio API silence detection if supported
      try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        if (AudioCtx) {
          const audioCtx = new AudioCtx();
          audioContextRef.current = audioCtx;
          const source = audioCtx.createMediaStreamSource(stream);
          const analyser = audioCtx.createAnalyser();
          analyser.fftSize = 256;
          analyser.smoothingTimeConstant = 0.3;
          source.connect(analyser);
          analyserRef.current = analyser;

          const checkAudioLevel = () => {
            if (!analyserRef.current || isCancelledRef.current) return;
            const data = new Uint8Array(analyserRef.current.frequencyBinCount);
            analyserRef.current.getByteFrequencyData(data);
            let sum = 0;
            for (let i = 0; i < data.length; i++) {
              sum += data[i];
            }
            const average = sum / data.length;

            if (average > 14) {
              hasSpokenRef.current = true;
              setHasDetectedSpeech(true);
              lastSpeechTimeRef.current = Date.now();
            } else if (hasSpokenRef.current && autoStopOnSilence) {
              const elapsedSilence = Date.now() - lastSpeechTimeRef.current;
              if (elapsedSilence > silenceDuration) {
                // User has finished speaking! Automatically stop turn and transcribe
                stopListening();
                return;
              }
            }

            silenceRafRef.current = requestAnimationFrame(checkAudioLevel);
          };

          silenceRafRef.current = requestAnimationFrame(checkAudioLevel);
        }
      } catch (audioCtxErr) {
        // Fallback gracefully without silence detection
        console.warn("Web Audio API not supported for VAD, manual turn stop available:", audioCtxErr);
      }

      const mimeType = getSupportedMimeType();
      const recorderOptions = mimeType ? { mimeType } : {};
      const mediaRecorder = new MediaRecorder(stream, recorderOptions);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        cleanupAudioNodes();

        // Release microphone hardware tracks between turns to respect browser permissions
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
        }

        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }

        setIsRecording(false);

        // If user cancelled or in-flight transcription exists, don't submit audio
        if (isCancelledRef.current) {
          setIsListening(false);
          setIsTranscribing(false);
          setInterimTranscript("");
          isTranscribingRef.current = false;
          return;
        }

        const audioBlob = new Blob(audioChunksRef.current, {
          type: mimeType || "audio/webm",
        });

        if (audioBlob.size === 0) {
          setIsListening(false);
          setIsTranscribing(false);
          setInterimTranscript("");
          isTranscribingRef.current = false;
          return;
        }

        // Send to FastAPI Cloud Whisper endpoint
        isTranscribingRef.current = true;
        setIsTranscribing(true);
        setInterimTranscript("Transcribing with Groq Whisper (cloud STT)...");

        try {
          const res = await api.transcribeAudio(audioBlob);
          const recognizedText = (res?.text || "").trim();
          setTranscriptionMeta(res);
          setIsTranscribing(false);
          setIsListening(false);
          setInterimTranscript("");
          isTranscribingRef.current = false;

          if (recognizedText) {
            setTranscript(recognizedText);
          } else {
            setError("No speech was detected. Please speak clearly.");
          }
        } catch (err) {
          setIsTranscribing(false);
          setIsListening(false);
          setInterimTranscript("");
          isTranscribingRef.current = false;
          setError(`Cloud Whisper transcription error: ${err.message}`);
        }
      };

      mediaRecorder.start(250); // Slice into 250ms chunks
      setIsListening(true);
      setIsRecording(true);

      // Start elapsed timer
      timerRef.current = setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      cleanupAudioNodes();
      setIsListening(false);
      setIsRecording(false);
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setError("Microphone permission was denied. Please allow microphone access in your browser settings.");
      } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        setError("No microphone device was found. Please connect a microphone.");
      } else {
        setError(`Could not access microphone: ${err.message}`);
      }
    }
  }, [cleanupAudioNodes, stopListening]);

  const cancelListening = useCallback(() => {
    isCancelledRef.current = true;
    cleanupAudioNodes();
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
    audioChunksRef.current = [];
    setIsListening(false);
    setIsRecording(false);
    setIsTranscribing(false);
    isTranscribingRef.current = false;
    setInterimTranscript("");
    setRecordingSeconds(0);
    hasSpokenRef.current = false;
    setHasDetectedSpeech(false);
  }, [cleanupAudioNodes]);

  const resetTranscript = useCallback(() => {
    setTranscript("");
    setInterimTranscript("");
    setError(null);
    setTranscriptionMeta(null);
    setRecordingSeconds(0);
    hasSpokenRef.current = false;
    setHasDetectedSpeech(false);
  }, []);

  return {
    isSupported,
    isListening,
    isRecording,
    isTranscribing,
    recordingSeconds,
    recordingTimeFormatted: formatTime(recordingSeconds),
    transcript,
    setTranscript,
    interimTranscript,
    error,
    transcriptionMeta,
    hasDetectedSpeech,
    startListening,
    stopListening,
    cancelListening,
    resetTranscript,
  };
}
