import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  AlertCircle,
  AlertTriangle,
  Edit3,
  Send,
  Loader2,
  FileCheck,
  Download,
  Save,
  Check,
  FileText,
} from "lucide-react";
import { api } from "../services/api";
import { storageService } from "../services/storageService";
import { useToast } from "../context/ToastContext";
import { useAuth } from "../context/AuthContext";
import Modal from "../components/common/Modal";

export default function ReviewFormPage({
  formId,
  formTitle,
  values: initialValues = {},
  pdfFilledFields: initialPdfFields = [],
  needsReviewFields: initialNeedsReview = {},
  manuallyEditedFields: initialManualFields = [],
  setView,
  initialSubmissionSuccess = null,
}) {
  const { user } = useAuth();
  const { toast } = useToast();

  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [exportingPdf, setExportingPdf] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [validationErrors, setValidationErrors] = useState([]);
  const [submissionSuccess, setSubmissionSuccess] = useState(initialSubmissionSuccess || null);
  const [submitModalOpen, setSubmitModalOpen] = useState(false);

  // Form values and extraction metadata
  const [values, setValues] = useState(() => {
    if (initialValues && Object.keys(initialValues).length > 0) {
      return { ...initialValues };
    }
    const saved = storageService.loadDraft(formId, user?.id);
    return saved || {};
  });

  const [pdfFilledFields, setPdfFilledFields] = useState(initialPdfFields || []);
  const [needsReviewFields, setNeedsReviewFields] = useState(initialNeedsReview || {});
  const [manuallyEditedFields, setManuallyEditedFields] = useState(initialManualFields || []);
  const [editingFieldKey, setEditingFieldKey] = useState(null);
  const [inlineEditValue, setInlineEditValue] = useState("");

  useEffect(() => {
    let isMounted = true;
    const load = async () => {
      setLoading(true);
      try {
        const data = await api.getForm(formId);
        if (isMounted) setForm(data);
      } catch (err) {
        toast(`Error loading form schema: ${err.message}`, "error");
      } finally {
        if (isMounted) setLoading(false);
      }
    };
    load();
    return () => {
      isMounted = false;
    };
  }, [formId, toast]);

  // Validate form fields before submission or export
  const validateForm = () => {
    if (!form?.schema_json?.fields) return true;
    const errors = [];
    const fields = form.schema_json.fields;

    for (const f of fields) {
      const val = values[f.name];

      // Required validation
      if (f.required) {
        if (
          val === undefined ||
          val === null ||
          (typeof val === "string" && !val.trim()) ||
          (f.type === "checkbox" && !val)
        ) {
          errors.push(`"${f.label}" is required.`);
          continue;
        }
      }

      // Format validations
      if (val !== undefined && val !== null && String(val).trim()) {
        const strVal = String(val).trim();
        if (f.type === "email") {
          const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
          if (!emailRegex.test(strVal)) {
            errors.push(`"${f.label}" must be a valid email address.`);
          }
        } else if (f.type === "phone") {
          const digitsOnly = strVal.replace(/\D/g, "");
          if (digitsOnly.length < 7 || digitsOnly.length > 15) {
            errors.push(`"${f.label}" must be a valid phone number (7-15 digits).`);
          }
        } else if (f.type === "url") {
          try {
            const parsed = new URL(strVal);
            if (!["http:", "https:"].includes(parsed.protocol)) {
              errors.push(`"${f.label}" must start with http:// or https://.`);
            }
          } catch {
            errors.push(`"${f.label}" must be a valid URL.`);
          }
        } else if (f.type === "number") {
          const num = Number(val);
          if (isNaN(num)) {
            errors.push(`"${f.label}" must be a numeric value.`);
          } else {
            if (f.min_value !== undefined && f.min_value !== null && num < Number(f.min_value)) {
              errors.push(`"${f.label}" must be at least ${f.min_value}.`);
            }
            if (f.max_value !== undefined && f.max_value !== null && num > Number(f.max_value)) {
              errors.push(`"${f.label}" must be at most ${f.max_value}.`);
            }
          }
        } else if (["text", "textarea"].includes(f.type)) {
          if (f.min_length !== undefined && f.min_length !== null && strVal.length < Number(f.min_length)) {
            errors.push(`"${f.label}" must be at least ${f.min_length} characters.`);
          }
          if (f.max_length !== undefined && f.max_length !== null && strVal.length > Number(f.max_length)) {
            errors.push(`"${f.label}" cannot exceed ${f.max_length} characters.`);
          }
        }
      }
    }

    setValidationErrors(errors);
    return errors.length === 0;
  };

  const handleOpenSubmitConfirm = () => {
    if (validateForm()) {
      setSubmitModalOpen(true);
    } else {
      toast("Please resolve required fields before submitting.", "error");
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setSubmitModalOpen(false);

    try {
      const response = await api.createSubmission(formId, values);
      setSubmissionSuccess(response);
      // Clean up local draft since form has been officially submitted
      storageService.deleteDraft(formId, user?.id);
      toast("Form response submitted and saved successfully!", "success");
    } catch (err) {
      if (err.details && Array.isArray(err.details)) {
        setValidationErrors(err.details);
      }
      toast(`Submission failed: ${err.message}`, "error");
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaveDraft = () => {
    setSavingDraft(true);
    try {
      storageService.saveDraft(formId, user?.id, values);
      toast("Progress saved to your personal draft.", "success");
    } catch (err) {
      toast(`Failed to save draft: ${err.message}`, "error");
    } finally {
      setSavingDraft(false);
    }
  };

  const handleExportPdf = async () => {
    // Validate first but allow export even if incomplete with a warning
    const isValid = validateForm();
    if (!isValid) {
      toast("Warning: Some required fields are incomplete, but generating preview PDF...", "info");
    }

    setExportingPdf(true);
    try {
      const cleanTitle = (form?.title || "Form").replace(/[^a-zA-Z0-9_-]/g, "_");
      await api.exportFormPdf(formId, values, `${cleanTitle}_Export.pdf`);
      toast("Completed form PDF exported successfully.", "success");
    } catch (err) {
      toast(`Failed to export PDF: ${err.message}`, "error");
    } finally {
      setExportingPdf(false);
    }
  };

  const handleStartInlineEdit = (fieldKey, currentVal) => {
    setEditingFieldKey(fieldKey);
    setInlineEditValue(currentVal !== undefined && currentVal !== null ? String(currentVal) : "");
  };

  const handleSaveInlineEdit = (fieldKey) => {
    setValues((prev) => {
      const updated = { ...prev, [fieldKey]: inlineEditValue };
      storageService.saveDraft(formId, user?.id, updated);
      return updated;
    });
    setManuallyEditedFields((prev) => Array.from(new Set([...prev, fieldKey])));
    // Clear review warning if user explicitly edited it
    if (needsReviewFields[fieldKey]) {
      setNeedsReviewFields((prev) => {
        const copy = { ...prev };
        delete copy[fieldKey];
        return copy;
      });
    }
    setEditingFieldKey(null);
    toast("Field value updated.", "info");
  };

  // Group fields into logical sections for review
  const categorizeFields = () => {
    const fields = form?.schema_json?.fields || [];
    const personal = [];
    const contact = [];
    const additional = [];

    fields.forEach((f) => {
      const name = f.name.toLowerCase();
      if (name.includes("name") || name.includes("birth") || name.includes("dob") || name.includes("gender")) {
        personal.push(f);
      } else if (name.includes("email") || name.includes("phone") || name.includes("mobile") || name.includes("address") || name.includes("city")) {
        contact.push(f);
      } else {
        additional.push(f);
      }
    });

    if (personal.length === 0 && contact.length === 0) {
      return [
        { title: "Primary Details", fields: fields.slice(0, Math.ceil(fields.length / 2)) },
        { title: "Additional Details", fields: fields.slice(Math.ceil(fields.length / 2)) },
      ];
    }

    return [
      { title: "Personal Information", fields: personal },
      { title: "Contact Information", fields: contact },
      { title: "Additional Details & Qualifications", fields: additional },
    ].filter((g) => g.fields.length > 0);
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto py-24 text-center">
        <div className="inline-block w-8 h-8 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-[#737373] mt-3 font-mono">Preparing form review...</p>
      </div>
    );
  }

  // Success view
  if (submissionSuccess) {
    return (
      <div className="max-w-xl mx-auto px-4 py-16 text-center space-y-6">
        <div className="w-16 h-16 rounded-2xl bg-neutral-900 text-white flex items-center justify-center mx-auto shadow-sm">
          <FileCheck className="w-8 h-8" />
        </div>

        <div>
          <h1 className="text-xl font-bold tracking-tight text-neutral-900">
            Form Submitted Successfully!
          </h1>
          <p className="text-xs text-[#737373] mt-1">
            Your response has been verified and permanently recorded.
          </p>
        </div>

        <div className="p-4 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl text-left text-xs space-y-2 font-mono">
          <div className="flex justify-between">
            <span className="text-neutral-500">Submission ID:</span>
            <span className="font-bold text-neutral-900">#{submissionSuccess.id}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-500">Form ID:</span>
            <span className="text-neutral-900">#{formId}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-neutral-500">Timestamp:</span>
            <span className="text-neutral-900">
              {new Date(submissionSuccess.created_at).toLocaleString()}
            </span>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-4">
          <button
            type="button"
            onClick={async () => {
              try {
                toast("Downloading official submission PDF...", "info");
                await api.downloadSubmissionPdf(
                  formId,
                  submissionSuccess.id,
                  `${form?.title || 'Form'}_Submission_${submissionSuccess.id}.pdf`
                );
                toast("PDF downloaded successfully.", "success");
              } catch (err) {
                toast(`PDF download failed: ${err.message}`, "error");
              }
            }}
            className="w-full sm:w-auto px-5 py-2.5 bg-neutral-900 hover:bg-black text-white rounded-lg text-xs font-semibold transition-all cursor-pointer shadow-xs flex items-center justify-center space-x-1.5"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Download Official PDF</span>
          </button>
          <button
            onClick={() => setView({ name: "submissions", formId, formTitle: form?.title })}
            className="w-full sm:w-auto px-5 py-2.5 border border-[#E5E5E5] hover:bg-neutral-50 text-neutral-800 rounded-lg text-xs font-semibold transition-all cursor-pointer"
          >
            View Submissions
          </button>
          <button
            onClick={() => setView({ name: "dashboard" })}
            className="w-full sm:w-auto px-5 py-2.5 border border-[#E5E5E5] hover:bg-neutral-50 text-neutral-800 rounded-lg text-xs font-semibold transition-all cursor-pointer"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const sections = categorizeFields();

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-8 py-8 text-left">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-[#E5E5E5] gap-4">
        <div className="flex items-center space-x-3">
          <button
            onClick={() =>
              setView({
                name: "fill",
                formId,
                formTitle: form?.title,
              })
            }
            className="p-1.5 rounded-lg border border-[#E5E5E5] hover:bg-neutral-100 text-neutral-600 hover:text-black transition-colors cursor-pointer"
            title="Back to Voice Assistant"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-tight text-neutral-900 break-words">
              Review Form Details
            </h1>
            <p className="text-xs text-[#737373] mt-0.5">
              Verify populated details, edit any field inline, save progress, or export a PDF.
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleSaveDraft}
            disabled={savingDraft}
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
            title="Save draft progress to your account"
          >
            <Save className="w-3.5 h-3.5 text-neutral-700" />
            <span>Save Draft</span>
          </button>

          <button
            type="button"
            onClick={handleExportPdf}
            disabled={exportingPdf}
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
            title="Export completed PDF independently without submitting"
          >
            {exportingPdf ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5 text-neutral-700" />
            )}
            <span>Export PDF</span>
          </button>

          <button
            disabled={submitting}
            onClick={handleOpenSubmitConfirm}
            className="px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors flex items-center space-x-1.5 cursor-pointer shadow-xs disabled:opacity-50"
          >
            <Send className="w-3.5 h-3.5" />
            <span>Submit Form</span>
          </button>
        </div>
      </div>

      {/* Review Warnings Alert */}
      {Object.keys(needsReviewFields).length > 0 && (
        <div className="mt-6 p-4 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 space-y-2">
          <div className="flex items-center space-x-1.5 font-semibold text-amber-950">
            <AlertTriangle className="w-4 h-4 text-amber-600" />
            <span>Uncertain or Ambiguous Values Extracted from PDF:</span>
          </div>
          <p className="text-[11px] text-amber-800">
            The AI detected ambiguity for the following fields. Please review and confirm or edit them before submitting:
          </p>
          <ul className="list-disc list-inside space-y-1 pl-1 text-[11px]">
            {Object.entries(needsReviewFields).map(([k, msg]) => {
              const label = form?.schema_json?.fields?.find((f) => f.name === k)?.label || k;
              return (
                <li key={k}>
                  <strong className="text-amber-950">{label}:</strong> {msg}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {/* Validation Errors Alert */}
      {validationErrors.length > 0 && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 space-y-1">
          <div className="flex items-center space-x-1.5 font-semibold">
            <AlertCircle className="w-4 h-4" />
            <span>Please resolve the following required fields:</span>
          </div>
          <ul className="list-disc list-inside space-y-0.5 pl-2 mt-1">
            {validationErrors.map((err, i) => (
              <li key={i}>{err}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Sectioned Information Summary Cards */}
      <div className="space-y-6 mt-8">
        {sections.map((sec, secIdx) => (
          <div
            key={secIdx}
            className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs"
          >
            <div className="flex items-center justify-between pb-3 border-b border-[#E5E5E5] mb-4">
              <h3 className="text-xs font-semibold text-neutral-900 uppercase tracking-wider">
                {sec.title}
              </h3>
              <button
                type="button"
                onClick={() =>
                  setView({
                    name: "fill",
                    formId,
                    formTitle: form?.title,
                  })
                }
                className="inline-flex items-center space-x-1 text-xs text-neutral-500 hover:text-black transition-colors cursor-pointer"
              >
                <Edit3 className="w-3 h-3" />
                <span>Edit via Assistant</span>
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {sec.fields.map((field) => {
                const val = values[field.name];
                const isEmpty =
                  val === undefined ||
                  val === null ||
                  String(val).trim() === "" ||
                  val === false;

                const isPdfFilled = pdfFilledFields.includes(field.name);
                const isManuallyEdited = manuallyEditedFields.includes(field.name);
                const isReviewNeeded = Boolean(needsReviewFields[field.name]);
                const isEditing = editingFieldKey === field.name;

                return (
                  <div
                    key={field.name}
                    className={`p-3 rounded-xl border text-xs transition-all ${
                      field.required && isEmpty
                        ? "border-red-300 bg-red-50/40"
                        : isReviewNeeded
                        ? "border-amber-300 bg-amber-50/30"
                        : "border-[#E5E5E5] bg-[#F7F7F7]"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-1 flex-wrap">
                      <span className="font-medium text-neutral-600 font-mono text-[11px]">
                        {field.label}
                      </span>
                      <div className="flex items-center space-x-1">
                        {isPdfFilled && (
                          <span
                            className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-blue-100 text-blue-800 font-semibold"
                            title="Populated from uploaded PDF"
                          >
                            📄 From PDF
                          </span>
                        )}
                        {isManuallyEdited && (
                          <span
                            className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-neutral-200 text-neutral-800 font-semibold"
                            title="Manually entered or corrected"
                          >
                            ✏️ Edited
                          </span>
                        )}
                        {isReviewNeeded && (
                          <span
                            className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-amber-200 text-amber-900 font-semibold"
                            title={needsReviewFields[field.name]}
                          >
                            ⚠️ Review
                          </span>
                        )}
                        {field.required && (
                          <span className="text-[10px] text-neutral-400 font-mono">
                            Required
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Value Display or Inline Edit Form */}
                    {isEditing ? (
                      <div className="mt-2 flex items-center space-x-1.5">
                        <input
                          type={field.type === "number" ? "number" : field.type === "date" ? "date" : "text"}
                          value={inlineEditValue}
                          onChange={(e) => setInlineEditValue(e.target.value)}
                          className="flex-1 px-2 py-1 text-xs border border-neutral-400 rounded bg-white focus:outline-none focus:border-black font-semibold text-neutral-900"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleSaveInlineEdit(field.name);
                            if (e.key === "Escape") setEditingFieldKey(null);
                          }}
                        />
                        <button
                          type="button"
                          onClick={() => handleSaveInlineEdit(field.name)}
                          className="p-1 rounded bg-neutral-900 text-white hover:bg-black transition-colors cursor-pointer"
                          title="Save value"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingFieldKey(null)}
                          className="px-1.5 py-1 text-[11px] text-neutral-500 hover:text-black cursor-pointer"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="mt-1 flex items-center justify-between">
                        <p className="font-semibold text-neutral-900 break-words text-sm">
                          {typeof val === "boolean"
                            ? val
                              ? "Yes / Checked"
                              : "No / Unchecked"
                            : val !== undefined && val !== null && String(val).trim() !== ""
                            ? String(val)
                            : "—"}
                        </p>
                        <button
                          type="button"
                          onClick={() => handleStartInlineEdit(field.name, val)}
                          className="text-[11px] text-neutral-400 hover:text-neutral-900 p-1 rounded hover:bg-neutral-200/60 transition-colors cursor-pointer"
                          title="Edit this field value"
                        >
                          <Edit3 className="w-3 h-3" />
                        </button>
                      </div>
                    )}

                    {isReviewNeeded && (
                      <p className="text-[10px] text-amber-800 mt-1 italic">
                        {needsReviewFields[field.name]}
                      </p>
                    )}

                    {field.required && isEmpty && (
                      <span className="text-[10px] text-red-600 font-medium block mt-1">
                        * Required value missing
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      {/* Bottom Actions */}
      <div className="mt-8 pt-6 border-t border-[#E5E5E5] flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() =>
              setView({
                name: "fill",
                formId,
                formTitle: form?.title,
              })
            }
            className="text-xs text-neutral-600 hover:text-black cursor-pointer"
          >
            ← Return to Assistant
          </button>
        </div>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={handleSaveDraft}
            disabled={savingDraft}
            className="px-3.5 py-2 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 transition-colors cursor-pointer flex items-center space-x-1.5"
          >
            <Save className="w-3.5 h-3.5 text-neutral-700" />
            <span>Save Draft</span>
          </button>

          <button
            type="button"
            onClick={handleExportPdf}
            disabled={exportingPdf}
            className="px-3.5 py-2 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 transition-colors cursor-pointer flex items-center space-x-1.5"
          >
            {exportingPdf ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Download className="w-3.5 h-3.5 text-neutral-700" />
            )}
            <span>Export Completed PDF</span>
          </button>

          <button
            type="button"
            disabled={submitting}
            onClick={handleOpenSubmitConfirm}
            className="inline-flex items-center space-x-2 px-5 py-2 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-all shadow-xs cursor-pointer disabled:opacity-50"
          >
            {submitting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Submitting...</span>
              </>
            ) : (
              <>
                <span>Submit Form Response</span>
                <Send className="w-3.5 h-3.5" />
              </>
            )}
          </button>
        </div>
      </div>

      {/* Confirmation Modal */}
      <Modal
        isOpen={submitModalOpen}
        onClose={() => setSubmitModalOpen(false)}
        title="Confirm Submission"
      >
        <div className="text-left text-xs text-neutral-700 space-y-3">
          <p>
            You are about to submit your response for{" "}
            <strong className="text-neutral-900 font-semibold">
              &quot;{form?.title}&quot;
            </strong>
            .
          </p>
          <p className="text-neutral-500">
            Please make sure that all populated and extracted values are accurate. Your response will be securely committed to the database.
          </p>
          <div className="pt-3 flex justify-end space-x-2">
            <button
              onClick={() => setSubmitModalOpen(false)}
              className="px-3 py-1.5 border border-[#E5E5E5] rounded-lg text-xs font-medium text-neutral-700 hover:bg-neutral-50 cursor-pointer"
            >
              Cancel
            </button>
            <button
              disabled={submitting}
              onClick={handleSubmit}
              className="px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer shadow-xs"
            >
              Confirm & Submit
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
