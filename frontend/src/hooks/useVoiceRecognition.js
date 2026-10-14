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

  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const streamRef = useRef(null);
  const timerRef = useRef(null);
  const isCancelledRef = useRef(false);

  // Formats elapsed seconds to "0:05" or "1:23"
  const formatTime = (secs) => {
    const mins = Math.floor(secs / 60);
    const remainder = secs % 60;
    return `${mins}:${remainder < 10 ? "0" : ""}${remainder}`;
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
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
  }, []);

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

  const startListening = useCallback(async () => {
    setError(null);
    setTranscript("");
    setInterimTranscript("");
    isCancelledRef.current = false;
    audioChunksRef.current = [];
    setRecordingSeconds(0);

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError("Audio recording is not supported in this browser environment.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      const mimeType = getSupportedMimeType();
      const options = mimeType ? { mimeType } : {};
      const mediaRecorder = new MediaRecorder(stream, options);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        // Stop stream tracks
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;

        if (timerRef.current) {
          clearInterval(timerRef.current);
          timerRef.current = null;
        }

        setIsRecording(false);

        // If user cancelled, don't call transcription
        if (isCancelledRef.current) {
          setIsListening(false);
          setIsTranscribing(false);
          setInterimTranscript("");
          return;
        }

        const audioBlob = new Blob(audioChunksRef.current, {
          type: mimeType || "audio/webm",
        });

        if (audioBlob.size === 0) {
          setIsListening(false);
          setIsTranscribing(false);
          setError("No audio data captured. Please speak again.");
          return;
        }

        // Send to FastAPI Cloud Whisper endpoint
        setIsTranscribing(true);
        setInterimTranscript("Transcribing with Groq Whisper (cloud STT)...");

        try {
          const res = await api.transcribeAudio(audioBlob);
          const recognizedText = (res?.text || "").trim();
          setTranscriptionMeta(res);
          setIsTranscribing(false);
          setIsListening(false);
          setInterimTranscript("");

          if (recognizedText) {
            setTranscript(recognizedText);
          } else {
            setError("No speech was detected in the recording. Please try again.");
          }
        } catch (err) {
          setIsTranscribing(false);
          setIsListening(false);
          setInterimTranscript("");
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
  }, []);

  const stopListening = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
      try {
        mediaRecorderRef.current.stop();
      } catch {
        // ignore
      }
    }
  }, []);

  const cancelListening = useCallback(() => {
    isCancelledRef.current = true;
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
    setInterimTranscript("");
    setRecordingSeconds(0);
  }, []);

  const resetTranscript = useCallback(() => {
    setTranscript("");
    setInterimTranscript("");
    setError(null);
    setTranscriptionMeta(null);
    setRecordingSeconds(0);
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
    startListening,
    stopListening,
    cancelListening,
    resetTranscript,
  };
}
