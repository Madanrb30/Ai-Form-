import React, { useEffect, useState } from "react";
import { api } from "../services/api";
import FormRenderer from "../components/FormRenderer";

export default function FormFillerPage({ formId, setView, voiceComponent }) {
  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [submittedId, setSubmittedId] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const fetchForm = async () => {
      setLoading(true);
      setServerError(null);
      try {
        const data = await api.getForm(formId);
        if (isMounted) {
          setForm(data);
          // Initialize defaults
          const initial = {};
          data.schema_json?.fields?.forEach((f) => {
            if (f.default_value !== null && f.default_value !== undefined) {
              initial[f.name] = f.default_value;
            } else if (f.type === "checkbox") {
              initial[f.name] = false;
            } else {
              initial[f.name] = "";
            }
          });
          setValues(initial);
        }
      } catch (err) {
        if (isMounted) {
          setServerError(`Failed to load form: ${err.message}`);
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchForm();
    return () => {
      isMounted = false;
    };
  }, [formId]);

  const validate = () => {
    const newErrors = {};
    const fields = form?.schema_json?.fields || [];

    for (const f of fields) {
      const val = values[f.name];

      // Required check
      if (f.required) {
        if (
          val === undefined ||
          val === null ||
          (typeof val === "string" && !val.trim()) ||
          (f.type === "checkbox" && !val)
        ) {
          newErrors[f.name] = `${f.label} is required.`;
          continue;
        }
      }

      // Format validations
      if (val !== undefined && val !== null && String(val).trim()) {
        if (f.type === "email") {
          const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
          if (!emailRegex.test(String(val))) {
            newErrors[f.name] = "Please enter a valid email address.";
          }
        } else if (f.type === "number") {
          if (isNaN(Number(val))) {
            newErrors[f.name] = "Please enter a valid number.";
          }
        }
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setServerError(null);

    if (!validate()) {
      return;
    }

    setSubmitting(true);
    try {
      const submission = await api.createSubmission(formId, values);
      setSubmittedId(submission.id);
    } catch (err) {
      if (err.details && Array.isArray(err.details)) {
        setServerError(`Validation failed: ${err.details.join(", ")}`);
      } else {
        setServerError(err.message || "Failed to submit form");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-20 text-center">
        <div className="inline-block w-6 h-6 border-2 border-zinc-900 border-t-transparent rounded-full animate-spin"></div>
        <p className="text-xs text-zinc-500 mt-2 font-mono">Loading form schema...</p>
      </div>
    );
  }

  if (serverError && !form) {
    return (
      <div className="max-w-3xl mx-auto px-4 py-12 text-left">
        <div className="p-4 bg-red-50 border border-red-200 text-sm text-red-700">
          <p className="font-semibold">Error</p>
          <p>{serverError}</p>
        </div>
        <button
          onClick={() => setView({ name: "dashboard" })}
          className="mt-4 px-4 py-2 bg-black text-white text-xs"
        >
          Back to Forms
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto px-4 sm:px-6 py-10">
      {/* Top Bar */}
      <div className="flex items-center justify-between pb-6 border-b border-zinc-200">
        <div>
          <button
            onClick={() => setView({ name: "dashboard" })}
            className="text-xs text-zinc-500 hover:text-black mb-1 flex items-center gap-1 cursor-pointer"
          >
            ← Back to Forms
          </button>
          <h1 className="text-2xl font-bold tracking-tight text-black m-0">
            {form?.title}
          </h1>
          {form?.description && (
            <p className="text-sm text-zinc-500 mt-1">{form.description}</p>
          )}
        </div>
        <button
          onClick={() => setView({ name: "submissions", formId })}
          className="px-3 py-1.5 border border-zinc-200 text-xs text-zinc-700 hover:border-black hover:text-black transition-colors"
        >
          View Submissions
        </button>
      </div>

      {/* Voice Assistant Slot (integrated in Phase 4) */}
      {voiceComponent && (
        <div className="mt-6">
          {voiceComponent({
            schema: form?.schema_json,
            values,
            setValues,
            setErrors,
          })}
        </div>
      )}

      {/* Success banner */}
      {submittedId && (
        <div className="mt-6 p-4 bg-emerald-50 border border-emerald-300 text-sm text-emerald-900 flex items-center justify-between text-left">
          <div>
            <p className="font-semibold">Submission received and saved! (ID: {submittedId})</p>
            <p className="text-xs text-emerald-700 mt-0.5">
              Your response is safely recorded in the database.
            </p>
          </div>
          <div className="flex space-x-2">
            <button
              onClick={() => {
                setSubmittedId(null);
                // reset form
                const initial = {};
                form?.schema_json?.fields?.forEach((f) => {
                  initial[f.name] = f.type === "checkbox" ? false : "";
                });
                setValues(initial);
                setErrors({});
              }}
              className="px-3 py-1.5 border border-emerald-400 bg-white text-xs text-emerald-900 font-medium hover:bg-emerald-100"
            >
              Fill Again
            </button>
            <button
              onClick={() => setView({ name: "submissions", formId })}
              className="px-3 py-1.5 bg-black text-white text-xs font-medium hover:bg-zinc-800"
            >
              View All Submissions
            </button>
          </div>
        </div>
      )}

      {/* Server error during submit */}
      {serverError && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 text-sm text-red-700 text-left">
          <p className="font-semibold">Submission Error</p>
          <p>{serverError}</p>
        </div>
      )}

      {/* Form Card */}
      <form
        onSubmit={handleSubmit}
        className="mt-8 bg-white border border-zinc-200 p-6 sm:p-8 text-left shadow-xs"
      >
        <FormRenderer
          schema={form?.schema_json}
          values={values}
          onChange={setValues}
          errors={errors}
          disabled={submitting}
        />

        <div className="mt-8 pt-6 border-t border-zinc-200 flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              const reset = {};
              form?.schema_json?.fields?.forEach((f) => {
                reset[f.name] = f.type === "checkbox" ? false : "";
              });
              setValues(reset);
              setErrors({});
            }}
            className="text-xs text-zinc-500 hover:text-black cursor-pointer"
          >
            Clear Form
          </button>

          <button
            type="submit"
            disabled={submitting}
            className="px-6 py-2.5 bg-black text-white text-sm font-medium hover:bg-zinc-800 disabled:bg-zinc-300 transition-colors"
          >
            {submitting ? "Submitting..." : "Submit Response"}
          </button>
        </div>
      </form>
    </div>
  );
}
