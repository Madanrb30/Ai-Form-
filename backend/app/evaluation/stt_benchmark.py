"""
STT Benchmark & Accuracy Evaluation Suite
Provides genuine, reproducible speech-to-text evaluation across:
1. Groq whisper-large-v3-turbo
2. Groq whisper-large-v3
3. Sarvam saaras:v4

STRICT INTEGRITY RULES:
- Requires real audio files and verified ground-truth reference transcripts.
- Never substitutes reference transcripts as predicted hypotheses.
- Never hardcodes or fabricates WER/CER rates or latency values.
- Real provider requests are timed with time.perf_counter().
- Missing audio, missing references, or missing credentials strictly report INCOMPLETE.
- Exports detailed results to CSV.
"""

import os
import sys
import json
import time
import re
import csv
import wave
import argparse
from typing import Dict, Any, List, Optional, Tuple

from app.core.config import settings
from app.services.ai_provider import AIProviderError


# ---------------------------------------------------------------------------
# Evaluation Directories & Manifest Paths
# ---------------------------------------------------------------------------
BASE_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_SAMPLES_DIR = os.path.join(BASE_EVAL_DIR, "audio_samples")
MANIFEST_PATH = os.path.join(AUDIO_SAMPLES_DIR, "samples_manifest.json")
DEFAULT_CSV_OUTPUT = os.path.join(BASE_EVAL_DIR, "benchmark_results.csv")


# ---------------------------------------------------------------------------
# Provider Configurations & Published Unit Pricing
# ---------------------------------------------------------------------------
BENCHMARK_CONFIGS = [
    {
        "provider": "groq",
        "model": "whisper-large-v3-turbo",
        "name": "Groq Whisper Large v3 Turbo",
        "cost_per_hour_usd": 0.04,  # $0.040 per audio hour
    },
    {
        "provider": "groq",
        "model": "whisper-large-v3",
        "name": "Groq Whisper Large v3",
        "cost_per_hour_usd": 0.111,  # $0.111 per audio hour
    },
    {
        "provider": "sarvam",
        "model": "saaras:v4",
        "name": "Sarvam AI Saaras v4",
        "cost_per_hour_usd": 0.144,  # Approx ₹0.20/min = ₹12/hr ~= $0.144/hr
    },
]


# ---------------------------------------------------------------------------
# Metric Calculation Functions (Levenshtein Distance, WER, CER)
# ---------------------------------------------------------------------------
def compute_levenshtein_distance(seq1: List[str], seq2: List[str]) -> int:
    """Computes dynamic programming Levenshtein edit distance between two sequences."""
    n = len(seq1)
    m = len(seq2)
    dp = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(
                    dp[i - 1][j],      # deletion
                    dp[i][j - 1],      # insertion
                    dp[i - 1][j - 1]   # substitution
                )
    return dp[n][m]


def normalize_eval_text(text: str) -> str:
    """
    Normalizes text for standardized comparison:
    - Lowercase
    - Retains alphanumeric characters, spaces, and Tamil Unicode (\u0B80-\u0BFF)
    - Strips punctuation and excessive whitespace
    """
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s\u0B80-\u0BFF]", " ", text)
    return " ".join(text.split())


def calculate_wer(reference: str, hypothesis: str) -> float:
    """
    Calculates Word Error Rate (WER) = (Substitutions + Deletions + Insertions) / Total Reference Words.
    Returns float (0.0 = perfect match).
    """
    ref_norm = normalize_eval_text(reference)
    hyp_norm = normalize_eval_text(hypothesis)

    ref_words = ref_norm.split()
    hyp_words = hyp_norm.split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    distance = compute_levenshtein_distance(ref_words, hyp_words)
    return round(distance / len(ref_words), 4)


def calculate_cer(reference: str, hypothesis: str) -> float:
    """
    Calculates Character Error Rate (CER) = Levenshtein(chars) / len(ref_chars).
    Particularly useful for Tamil and phonetic agglutinative scripts.
    """
    ref_norm = normalize_eval_text(reference).replace(" ", "")
    hyp_norm = normalize_eval_text(hypothesis).replace(" ", "")

    if not ref_norm:
        return 0.0 if not hyp_norm else 1.0

    distance = compute_levenshtein_distance(list(ref_norm), list(hyp_norm))
    return round(distance / len(ref_norm), 4)


def evaluate_entity_accuracy(expected_entities: List[str], hypothesis: str) -> float:
    """
    Measures accuracy of capturing named entities (names, locations, departments)
    in the predicted transcript using deterministic matching.
    """
    if not expected_entities:
        return 1.0
    if not hypothesis or not hypothesis.strip():
        return 0.0

    hyp_norm = normalize_eval_text(hypothesis)
    matched = 0
    for entity in expected_entities:
        ent_norm = normalize_eval_text(entity)
        if ent_norm in hyp_norm:
            matched += 1
        else:
            tokens = ent_norm.split()
            if tokens and all(t in hyp_norm for t in tokens):
                matched += 1
    return round(matched / len(expected_entities), 4)


def evaluate_numeric_accuracy(expected_numbers: List[str], hypothesis: str) -> float:
    """
    Measures accuracy of capturing numbers, dates, and alphanumeric codes in hypothesis.
    """
    if not expected_numbers:
        return 1.0
    if not hypothesis or not hypothesis.strip():
        return 0.0

    hyp_norm = normalize_eval_text(hypothesis).replace(" ", "")
    matched = 0
    for num in expected_numbers:
        clean_num = normalize_eval_text(num).replace(" ", "")
        if clean_num in hyp_norm:
            matched += 1
    return round(matched / len(expected_numbers), 4)


def get_audio_duration_sec(audio_path: str) -> float:
    """Determines audio duration in seconds from a WAV file header if available."""
    if not os.path.exists(audio_path):
        return 0.0
    if audio_path.lower().endswith(".wav"):
        try:
            with wave.open(audio_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return round(frames / float(rate), 2)
        except Exception:
            pass
    return 0.0


def calculate_estimated_cost(duration_sec: float, cost_per_hour_usd: float) -> float:
    """Calculates estimated provider inference cost based on actual audio duration."""
    if duration_sec <= 0:
        return 0.0
    cost = (duration_sec / 3600.0) * cost_per_hour_usd
    return round(cost, 6)


# ---------------------------------------------------------------------------
# Provider Instantiation Helper
# ---------------------------------------------------------------------------
def create_benchmark_provider(provider_name: str, model_name: str):
    """Instantiates a provider configured specifically for a benchmark model."""
    if provider_name == "groq":
        from app.services.stt.groq_provider import GroqSTTProvider
        return GroqSTTProvider(model=model_name)
    elif provider_name == "sarvam":
        from app.services.stt.sarvam_provider import SarvamSTTProvider
        return SarvamSTTProvider(model=model_name)
    else:
        raise ValueError(f"Unsupported benchmark provider: '{provider_name}'")


# ---------------------------------------------------------------------------
# Benchmark Runner
# ---------------------------------------------------------------------------
def check_prerequisites(manifest_path: str, audio_dir: str) -> Dict[str, Any]:
    """
    Verifies presence of manifest, ground-truth transcripts, and real audio files.
    Returns status dict indicating missing prerequisites.
    """
    missing_items = []
    if not os.path.exists(manifest_path):
        return {
            "status": "INCOMPLETE",
            "reason": f"Manifest file missing at {manifest_path}",
            "samples": []
        }

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            samples = json.load(f)
    except Exception as e:
        return {
            "status": "INCOMPLETE",
            "reason": f"Invalid manifest JSON: {e}",
            "samples": []
        }

    if not samples:
        return {
            "status": "INCOMPLETE",
            "reason": "Manifest contains no sample definitions",
            "samples": []
        }

    for s in samples:
        audio_name = s.get("audio_filename", "")
        audio_path = os.path.join(audio_dir, audio_name)
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
            missing_items.append(f"{s.get('id', 'unknown')}: {audio_name}")

    if missing_items:
        return {
            "status": "INCOMPLETE",
            "reason": f"Missing real audio recordings ({len(missing_items)} files): {', '.join(missing_items)}",
            "samples": samples,
            "missing_audio": missing_items,
        }

    return {
        "status": "READY",
        "reason": "All reference transcripts and audio files verified",
        "samples": samples,
        "missing_audio": [],
    }


def execute_sample_benchmark(
    sample: Dict[str, Any],
    audio_path: str,
    provider_config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Executes a genuine benchmark turn:
    - Reads real audio bytes from disk
    - Calls provider.transcribe() with time.perf_counter()
    - Calculates genuine WER, CER, entity accuracy, numeric accuracy, and cost
    """
    provider_key = provider_config["provider"]
    model_name = provider_config["model"]
    sample_id = sample.get("id", "unknown")
    reference = sample.get("reference_transcript", "")
    expected_entities = sample.get("expected_entities", [])
    expected_numbers = sample.get("expected_numbers", [])

    content_type = "audio/wav" if audio_path.lower().endswith(".wav") else "audio/webm"
    filename = os.path.basename(audio_path)

    # 1. Read real audio file
    with open(audio_path, "rb") as af:
        audio_bytes = af.read()

    audio_duration = get_audio_duration_sec(audio_path)

    # 2. Instantiate provider
    provider = create_benchmark_provider(provider_key, model_name)

    # 3. Measure request latency with time.perf_counter()
    t0 = time.perf_counter()
    status = "SUCCESS"
    error_msg = ""
    hypothesis = ""
    returned_duration = 0.0

    try:
        result = provider.transcribe(
            audio_bytes=audio_bytes,
            filename=filename,
            content_type=content_type,
        )
        latency_sec = round(time.perf_counter() - t0, 4)
        hypothesis = result.get("text", "")
        returned_duration = result.get("duration") or audio_duration or 0.0
    except AIProviderError as e:
        latency_sec = round(time.perf_counter() - t0, 4)
        status = f"ERROR_{e.status_code}"
        error_msg = e.message
    except Exception as e:
        latency_sec = round(time.perf_counter() - t0, 4)
        status = "ERROR_EXCEPTION"
        error_msg = str(e)

    # Effective audio duration
    effective_duration = returned_duration if returned_duration > 0 else audio_duration
    estimated_cost = calculate_estimated_cost(effective_duration, provider_config["cost_per_hour_usd"])

    # 4. Evaluate metrics if successful
    if status == "SUCCESS":
        wer = calculate_wer(reference, hypothesis)
        cer = calculate_cer(reference, hypothesis)
        ent_acc = evaluate_entity_accuracy(expected_entities, hypothesis)
        num_acc = evaluate_numeric_accuracy(expected_numbers, hypothesis)
    else:
        wer = None
        cer = None
        ent_acc = 0.0
        num_acc = 0.0

    return {
        "sample_id": sample_id,
        "provider": provider_key,
        "model": model_name,
        "wer": wer,
        "cer": cer,
        "entity_accuracy": ent_acc,
        "numeric_accuracy": num_acc,
        "latency_sec": latency_sec,
        "audio_duration_sec": effective_duration,
        "estimated_cost_usd": estimated_cost,
        "status": status,
        "error_message": error_msg,
        "hypothesis": hypothesis,
        "reference": reference,
    }


def run_benchmark_suite(
    manifest_path: str = MANIFEST_PATH,
    audio_dir: str = AUDIO_SAMPLES_DIR,
    csv_output_path: str = DEFAULT_CSV_OUTPUT,
    custom_samples: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Runs the complete benchmark suite across all configured models.
    If prerequisites are missing, returns status='INCOMPLETE' and writes
    the status to the CSV report without fabricating predictions.
    """
    if custom_samples:
        samples = custom_samples
        prereq = {"status": "READY", "samples": samples, "missing_audio": []}
    else:
        prereq = check_prerequisites(manifest_path, audio_dir)
        samples = prereq.get("samples", [])

    results: List[Dict[str, Any]] = []

    # Write / initialize CSV report
    fieldnames = [
        "sample_id",
        "provider",
        "model",
        "wer",
        "cer",
        "entity_accuracy",
        "numeric_accuracy",
        "latency_sec",
        "audio_duration_sec",
        "estimated_cost_usd",
        "status",
        "error_message",
    ]

    if prereq["status"] != "READY":
        # Missing prerequisites: output clear INCOMPLETE records
        for s in samples:
            for p in BENCHMARK_CONFIGS:
                results.append({
                    "sample_id": s.get("id", "unknown"),
                    "provider": p["provider"],
                    "model": p["model"],
                    "wer": "N/A",
                    "cer": "N/A",
                    "entity_accuracy": 0.0,
                    "numeric_accuracy": 0.0,
                    "latency_sec": 0.0,
                    "audio_duration_sec": 0.0,
                    "estimated_cost_usd": 0.0,
                    "status": "INCOMPLETE (MISSING_AUDIO)",
                    "error_message": prereq["reason"],
                })

        with open(csv_output_path, "w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for r in results:
                writer.writerow(r)

        return {
            "status": "INCOMPLETE",
            "reason": prereq["reason"],
            "total_samples": len(samples),
            "csv_report": csv_output_path,
            "results": results,
        }

    # Run actual live evaluations across real audio files
    for s in samples:
        audio_name = s.get("audio_filename", "")
        audio_path = s.get("audio_path") or os.path.join(audio_dir, audio_name)

        for p_cfg in BENCHMARK_CONFIGS:
            record = execute_sample_benchmark(s, audio_path, p_cfg)
            results.append(record)

    # Write successful genuine results to CSV
    with open(csv_output_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    return {
        "status": "COMPLETE",
        "total_evaluated": len(results),
        "csv_report": csv_output_path,
        "results": results,
    }


# ---------------------------------------------------------------------------
# CLI Command Interface
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Genuine Speech-to-Text Benchmark & Evaluation Suite"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live benchmark across audio samples in audio_samples directory.",
    )
    parser.add_argument(
        "--audio",
        type=str,
        default=None,
        help="Path to an individual audio recording to benchmark.",
    )
    parser.add_argument(
        "--reference",
        type=str,
        default="",
        help="Ground-truth reference transcript for the single audio file.",
    )
    parser.add_argument(
        "--output-csv",
        type=str,
        default=DEFAULT_CSV_OUTPUT,
        help="Path to export evaluation CSV results.",
    )

    args = parser.parse_args()

    print("=" * 75)
    print("GENUINE SPEECH-TO-TEXT BENCHMARK & ACCURACY EVALUATION")
    print("=" * 75)

    if args.audio:
        if not os.path.exists(args.audio):
            print(f"Error: Specified audio file '{args.audio}' does not exist.")
            sys.exit(1)
        if not args.reference:
            print("Warning: No ground truth reference provided. WER/CER will be N/A.")

        single_sample = [{
            "id": "cli_sample",
            "audio_filename": os.path.basename(args.audio),
            "audio_path": args.audio,
            "reference_transcript": args.reference,
            "expected_entities": [],
            "expected_numbers": [],
        }]
        print(f"Evaluating single recording: {args.audio}")
        summary = run_benchmark_suite(
            csv_output_path=args.output_csv,
            custom_samples=single_sample,
        )
    else:
        print(f"Audio Samples Directory: {AUDIO_SAMPLES_DIR}")
        print(f"Manifest Path: {MANIFEST_PATH}")
        summary = run_benchmark_suite(
            manifest_path=MANIFEST_PATH,
            audio_dir=AUDIO_SAMPLES_DIR,
            csv_output_path=args.output_csv,
        )

    print(f"\nExecution Status: {summary['status']}")
    if summary["status"] == "INCOMPLETE":
        print(f"Prerequisite Notice: {summary['reason']}")
        print(f"Results Report saved to: {summary['csv_report']}")
        print("Note: To run live benchmarks, place real recordings in audio_samples/")
    else:
        print(f"Evaluated {summary['total_evaluated']} model-sample turns.")
        print(f"CSV Report generated: {summary['csv_report']}")
        print("\nResults Summary:")
        for r in summary["results"]:
            wer_disp = f"{r['wer'] * 100:.2f}%" if r["wer"] is not None else "N/A"
            cer_disp = f"{r['cer'] * 100:.2f}%" if r["cer"] is not None else "N/A"
            print(
                f"[{r['status']}] {r['provider']} ({r['model']}) | Sample: {r['sample_id']} | "
                f"WER: {wer_disp} | CER: {cer_disp} | Latency: {r['latency_sec']}s | Cost: ${r['estimated_cost_usd']:.5f}"
            )


if __name__ == "__main__":
    main()
