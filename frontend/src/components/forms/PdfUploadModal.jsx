import React, { useState, useRef } from "react";
import {
  Upload,
  FileText,
  X,
  AlertCircle,
  Loader2,
  CheckCircle2,
  Shield,
  AlertTriangle,
  RotateCcw,
} from "lucide-react";
import Modal from "../common/Modal";
import { api } from "../../services/api";

export default function PdfUploadModal({
  isOpen,
  onClose,
  formId,
  formTitle,
  onExtractionSuccess,
}) {
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [error, setError] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [processingStep, setProcessingStep] = useState("");
  const [progressPercent, setProgressPercent] = useState(0);
  const [extractionResult, setExtractionResult] = useState(null);

  const fileInputRef = useRef(null);
  const abortControllerRef = useRef(null);
  const progressTimerRef = useRef(null);

  const resetState = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (progressTimerRef.current) {
      clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    setFile(null);
    setError(null);
    setProcessing(false);
    setProcessingStep("");
    setProgressPercent(0);
    setExtractionResult(null);
  };

  const handleClose = () => {
    if (processing) {
      if (window.confirm("An extraction is currently in progress. Cancel processing?")) {
        resetState();
        onClose();
      }
    } else {
      resetState();
      onClose();
    }
  };

  const validateFile = (selectedFile) => {
    setError(null);
    if (!selectedFile) return false;

    const fileName = selectedFile.name.toLowerCase();
    if (!fileName.endsWith(".pdf")) {
      setError("Unsupported file format. Please upload a PDF document (.pdf).");
      return false;
    }

    if (selectedFile.size === 0) {
      setError("The selected file is empty (0 bytes). Please upload a valid PDF.");
      return false;
    }

    // 15 MB limit
    const maxSizeBytes = 15 * 1024 * 1024;
    if (selectedFile.size > maxSizeBytes) {
      setError("File exceeds the maximum 15 MB limit. Please upload a smaller document.");
      return false;
    }

    return true;
  };

  const handleFileChange = (e) => {
    const selected = e.target.files?.[0];
    if (selected && validateFile(selected)) {
      setFile(selected);
      setError(null);
      setExtractionResult(null);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && validateFile(droppedFile)) {
      setFile(droppedFile);
      setError(null);
      setExtractionResult(null);
    }
  };

  const handleCancelProcessing = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (progressTimerRef.current) {
      clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
    setProcessing(false);
    setProgressPercent(0);
    setProcessingStep("");
    setError("Document extraction was cancelled by user.");
  };

  const handleStartExtraction = async () => {
    if (!file || processing) return;

    setError(null);
    setProcessing(true);
    setProgressPercent(15);
    setProcessingStep("Uploading PDF document...");

    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Simulated stepped progression for user feedback
    let currentStep = 15;
    progressTimerRef.current = setInterval(() => {
      if (currentStep < 85) {
        currentStep += 12;
        setProgressPercent(currentStep);
        if (currentStep >= 35 && currentStep < 60) {
          setProcessingStep("Reading pages & normalizing document text...");
        } else if (currentStep >= 60) {
          setProcessingStep("Extracting personal details & mapping to form fields...");
        }
      }
    }, 450);

    try {
      const result = await api.extractPdfForForm(formId, file, {
        signal: controller.signal,
      });

      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current);
        progressTimerRef.current = null;
      }

      setProgressPercent(100);
      setProcessingStep("Extraction complete!");
      setExtractionResult(result);
      setProcessing(false);

      // Notify parent page
      if (onExtractionSuccess) {
        onExtractionSuccess(result);
      }
    } catch (err) {
      if (progressTimerRef.current) {
        clearInterval(progressTimerRef.current);
        progressTimerRef.current = null;
      }
      setProcessing(false);
      setProgressPercent(0);
      setProcessingStep("");

      if (err.name === "AbortError" || controller.signal.aborted) {
        setError("Processing cancelled.");
      } else {
        const msg = err.message || "Failed to extract information from the PDF.";
        setError(msg);
      }
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Auto-Fill Form with PDF" maxWidth="max-w-lg">
      <div className="text-left text-xs text-neutral-700 space-y-4">
        {/* Intro Description */}
        <p className="text-neutral-600 text-xs leading-relaxed">
          Upload a personal document (such as a resume, profile, or application) to automatically extract and populate details into{" "}
          <strong className="text-neutral-900 font-semibold">&quot;{formTitle || "this form"}&quot;</strong>.
        </p>

        {/* Dropzone Area */}
        {!extractionResult && (
          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => !processing && fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all ${
              dragActive
                ? "border-neutral-900 bg-neutral-100"
                : file
                ? "border-neutral-900 bg-neutral-50"
                : "border-[#E5E5E5] hover:border-neutral-400 bg-[#FAFAFA]"
            } ${processing ? "pointer-events-none opacity-60" : ""}`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,application/pdf"
              onChange={handleFileChange}
              className="hidden"
              disabled={processing}
            />

            {file ? (
              <div className="space-y-2">
                <div className="w-10 h-10 rounded-lg bg-neutral-900 text-white mx-auto flex items-center justify-center">
                  <FileText className="w-5 h-5" />
                </div>
                <p className="font-semibold text-neutral-900 text-xs break-all">{file.name}</p>
                <p className="text-[11px] text-neutral-500 font-mono">
                  {(file.size / (1024 * 1024)).toFixed(2)} MB • PDF Document
                </p>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                    setError(null);
                  }}
                  className="text-[11px] text-red-600 hover:text-red-800 underline cursor-pointer mt-1 font-medium"
                >
                  Remove & Choose Another
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="w-10 h-10 rounded-lg bg-white border border-[#E5E5E5] text-neutral-700 mx-auto flex items-center justify-center shadow-2xs">
                  <Upload className="w-5 h-5 text-neutral-800" />
                </div>
                <p className="font-semibold text-neutral-900 text-xs">
                  Click to select or drag and drop your PDF here
                </p>
                <p className="text-[11px] text-neutral-400 font-mono">
                  Supported format: PDF only • Maximum file size: 15 MB
                </p>
              </div>
            )}
          </div>
        )}

        {/* In-Flight Processing Indicator & Cancel Option */}
        {processing && (
          <div className="p-4 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl space-y-3">
            <div className="flex items-center justify-between text-xs font-mono">
              <span className="font-semibold text-neutral-800 flex items-center space-x-2">
                <Loader2 className="w-3.5 h-3.5 animate-spin text-neutral-900" />
                <span>{processingStep}</span>
              </span>
              <span className="text-neutral-500">{progressPercent}%</span>
            </div>

            <div className="w-full bg-neutral-200 h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-neutral-900 h-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>

            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={handleCancelProcessing}
                className="px-2.5 py-1 text-[11px] border border-neutral-300 hover:border-black rounded text-neutral-700 hover:text-black transition-colors cursor-pointer"
              >
                Cancel Processing
              </button>
            </div>
          </div>
        )}

        {/* Error Alert */}
        {error && (
          <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-start space-x-2">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5 text-red-600" />
            <div className="flex-1">
              <p className="font-semibold">Extraction Failed</p>
              <p className="mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Successful Result Summary Card */}
        {extractionResult && (
          <div className="p-4 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl space-y-3">
            <div className="flex items-center space-x-2 text-emerald-700 font-semibold text-xs">
              <CheckCircle2 className="w-4 h-4" />
              <span>Extraction Completed Successfully</span>
            </div>

            <p className="text-xs text-neutral-700">{extractionResult.message}</p>

            <div className="grid grid-cols-3 gap-2 pt-1 font-mono text-[11px]">
              <div className="p-2 bg-white border border-[#E5E5E5] rounded-lg">
                <span className="text-neutral-400 block text-[10px]">Populated</span>
                <span className="font-bold text-neutral-900 text-sm">{extractionResult.total_matched}</span>
              </div>
              <div className="p-2 bg-white border border-[#E5E5E5] rounded-lg">
                <span className="text-neutral-400 block text-[10px]">Missing Req.</span>
                <span className="font-bold text-neutral-900 text-sm">
                  {extractionResult.missing_required_fields?.length || 0}
                </span>
              </div>
              <div className="p-2 bg-white border border-[#E5E5E5] rounded-lg">
                <span className="text-neutral-400 block text-[10px]">Review Flags</span>
                <span className="font-bold text-neutral-900 text-sm">
                  {Object.keys(extractionResult.needs_review || {}).length}
                </span>
              </div>
            </div>

            {Object.keys(extractionResult.needs_review || {}).length > 0 && (
              <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-lg text-[11px] text-amber-900 space-y-1">
                <div className="flex items-center space-x-1 font-semibold">
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
                  <span>Ambiguous fields marked for your confirmation</span>
                </div>
                <p className="text-neutral-600">
                  Review badges have been placed on fields that had multiple candidate matches.
                </p>
              </div>
            )}
          </div>
        )}

        {/* Privacy Disclosure Notice */}
        <div className="flex items-start space-x-2 pt-1 text-[11px] text-neutral-500 border-t border-neutral-100">
          <Shield className="w-3.5 h-3.5 text-neutral-700 shrink-0 mt-0.5" />
          <p>
            <strong className="text-neutral-700 font-medium">Privacy Notice:</strong> Your PDF is processed securely in memory to match fields in this published form. Document contents are not stored permanently on disk or exposed through public links.
          </p>
        </div>

        {/* Modal Actions */}
        <div className="pt-2 flex items-center justify-end space-x-2 border-t border-[#E5E5E5]">
          <button
            type="button"
            onClick={handleClose}
            className="px-3.5 py-1.5 border border-[#E5E5E5] hover:bg-neutral-50 rounded-lg text-xs font-medium text-neutral-700 transition-colors cursor-pointer"
          >
            {extractionResult ? "Done" : "Cancel"}
          </button>

          {!extractionResult ? (
            <button
              type="button"
              disabled={!file || processing}
              onClick={handleStartExtraction}
              className="px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 flex items-center space-x-1.5 cursor-pointer shadow-xs"
            >
              {processing ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Extracting...</span>
                </>
              ) : (
                <>
                  <Upload className="w-3.5 h-3.5" />
                  <span>Extract & Auto-Fill</span>
                </>
              )}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => {
                resetState();
              }}
              className="px-3.5 py-1.5 border border-neutral-300 hover:bg-neutral-50 rounded-lg text-xs font-medium text-neutral-700 transition-colors flex items-center space-x-1 cursor-pointer"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Upload Another</span>
            </button>
          )}
        </div>
      </div>
    </Modal>
  );
}
