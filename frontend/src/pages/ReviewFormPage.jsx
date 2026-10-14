import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  AlertCircle,
  Edit3,
  Send,
  Loader2,
  FileCheck,
} from "lucide-react";
import { api } from "../services/api";
import { storageService } from "../services/storageService";
import { useToast } from "../context/ToastContext";
import Modal from "../components/common/Modal";

export default function ReviewFormPage({ formId, values = {}, setView }) {
  const { toast } = useToast();

  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [validationErrors, setValidationErrors] = useState([]);
  const [submissionSuccess, setSubmissionSuccess] = useState(null);
  const [submitModalOpen, setSubmitModalOpen] = useState(false);

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

  // Validate form fields before submission
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
        if (f.type === "email") {
          const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
          if (!emailRegex.test(String(val))) {
            errors.push(`"${f.label}" must be a valid email address.`);
          }
        } else if (f.type === "number") {
          if (isNaN(Number(val))) {
            errors.push(`"${f.label}" must be a numeric value.`);
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
      toast("Please resolve validation errors before submitting.", "error");
    }
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    setSubmitModalOpen(false);

    try {
      const response = await api.createSubmission(formId, values);
      setSubmissionSuccess(response);
      // Clean up local draft since form has been officially submitted
      storageService.deleteDraft(formId);
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

  // Group fields into 3 logical sections for review
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

    // If grouping is uneven, balance them
    if (personal.length === 0 && contact.length === 0) {
      return [
        { title: "Primary Details", fields: fields.slice(0, Math.ceil(fields.length / 2)) },
        { title: "Additional Details", fields: fields.slice(Math.ceil(fields.length / 2)) },
      ];
    }

    return [
      { title: "Personal Information", fields: personal },
      { title: "Contact Information", fields: contact },
      { title: "Additional Details & Preferences", fields: additional },
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
        <div className="w-16 h-16 rounded-2xl bg-emerald-50 border border-emerald-200 text-emerald-600 flex items-center justify-center mx-auto shadow-sm">
          <FileCheck className="w-8 h-8" />
        </div>

        <div>
          <h1 className="text-xl font-bold tracking-tight text-neutral-900">
            Form Submitted Successfully!
          </h1>
          <p className="text-xs text-[#737373] mt-1">
            Your response has been verified and permanently committed to the SQLite database.
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
            onClick={() => setView({ name: "submissions", formId, formTitle: form?.title })}
            className="w-full sm:w-auto px-5 py-2.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-all cursor-pointer shadow-xs"
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
          <div>
            <h1 className="text-xl font-bold tracking-tight text-neutral-900">
              Review Your Form
            </h1>
            <p className="text-xs text-[#737373] mt-0.5">
              Please check all the details before final submission.
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() =>
              setView({
                name: "editor",
                formId,
                formTitle: form?.title,
              })
            }
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors cursor-pointer"
          >
            Back to Edit
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
                onClick={() =>
                  setView({
                    name: "editor",
                    formId,
                    formTitle: form?.title,
                  })
                }
                className="inline-flex items-center space-x-1 text-xs text-neutral-500 hover:text-black transition-colors cursor-pointer"
              >
                <Edit3 className="w-3 h-3" />
                <span>Edit Section</span>
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

                return (
                  <div
                    key={field.name}
                    className={`p-3 rounded-xl border text-xs ${
                      field.required && isEmpty
                        ? "border-red-300 bg-red-50/50"
                        : "border-[#E5E5E5] bg-[#F7F7F7]"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-neutral-500 font-mono text-[11px]">
                        {field.label}
                      </span>
                      {field.required && (
                        <span className="text-[10px] text-neutral-400 font-mono">
                          Required
                        </span>
                      )}
                    </div>
                    <p className="mt-1 font-semibold text-neutral-900 break-words text-sm">
                      {typeof val === "boolean"
                        ? val
                          ? "Yes / Checked"
                          : "No / Unchecked"
                        : val && String(val).trim() !== ""
                        ? String(val)
                        : "—"}
                    </p>
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

      {/* Bottom Submit Action */}
      <div className="mt-8 pt-6 border-t border-[#E5E5E5] flex items-center justify-between">
        <button
          onClick={() =>
            setView({
              name: "editor",
              formId,
              formTitle: form?.title,
            })
          }
          className="text-xs text-neutral-600 hover:text-black cursor-pointer"
        >
          ← Return to Editor
        </button>

        <button
          disabled={submitting}
          onClick={handleOpenSubmitConfirm}
          className="inline-flex items-center space-x-2 px-6 py-2.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-all shadow-xs cursor-pointer disabled:opacity-50"
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
            Please make sure that the populated values are accurate. Your response will be saved directly into the SQLite database.
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
