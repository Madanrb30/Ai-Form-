import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  Save,
  Mic,
  ArrowRight,
  CheckCircle2,
  Sparkles,
  RotateCcw,
  AlertCircle,
} from "lucide-react";
import { api } from "../services/api";
import { storageService } from "../services/storageService";
import { useToast } from "../context/ToastContext";
import FormRenderer from "../components/forms/FormRenderer";

export default function FormEditorPage({ formId, formTitle, setView }) {
  const { toast } = useToast();

  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const [values, setValues] = useState({});
  const [errors, setErrors] = useState({});
  const [aiFilledFields, setAiFilledFields] = useState([]);

  useEffect(() => {
    let isMounted = true;
    const fetchForm = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getForm(formId);
        if (!isMounted) return;
        setForm(data);

        // Check for draft
        const draft = storageService.getDraft(formId);
        const initial = {};

        data.schema_json?.fields?.forEach((f) => {
          if (draft?.values?.[f.name] !== undefined) {
            initial[f.name] = draft.values[f.name];
          } else if (f.default_value !== null && f.default_value !== undefined) {
            initial[f.name] = f.default_value;
          } else if (f.type === "checkbox") {
            initial[f.name] = false;
          } else {
            initial[f.name] = "";
          }
        });

        setValues(initial);
      } catch (err) {
        if (isMounted) setError(err.message || "Failed to load form");
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    fetchForm();
    return () => {
      isMounted = false;
    };
  }, [formId]);

  const handleSaveDraft = async () => {
    setSaving(true);
    try {
      storageService.saveDraft(formId, values, form?.title || "Form Draft");
      toast("Form draft successfully saved.", "success");
    } catch (err) {
      toast(`Failed to save draft: ${err.message}`, "error");
    } finally {
      setSaving(false);
    }
  };

  // Calculate Progress
  const fields = form?.schema_json?.fields || [];
  const requiredFields = fields.filter((f) => f.required);
  const filledRequiredCount = requiredFields.filter((f) => {
    const val = values[f.name];
    return val !== undefined && val !== null && String(val).trim() !== "" && val !== false;
  }).length;

  const totalFilled = fields.filter((f) => {
    const val = values[f.name];
    return val !== undefined && val !== null && String(val).trim() !== "" && val !== false;
  }).length;

  const progressPercent =
    requiredFields.length > 0
      ? Math.round((filledRequiredCount / requiredFields.length) * 100)
      : Math.round((totalFilled / Math.max(1, fields.length)) * 100);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto py-24 text-center">
        <div className="inline-block w-8 h-8 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-[#737373] mt-3 font-mono">Loading form editor...</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-8 py-8 text-left">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-[#E5E5E5] gap-4">
        <div className="flex items-center space-x-3">
          <button
            onClick={() => setView({ name: "dashboard" })}
            className="p-1.5 rounded-lg border border-[#E5E5E5] hover:bg-neutral-100 text-neutral-600 hover:text-black transition-colors cursor-pointer"
            title="Back to Dashboard"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-neutral-900">
              {form?.title}
            </h1>
            <p className="text-xs text-[#737373] mt-0.5">
              Smart Form Editor • Review and modify field values
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={() =>
              setView({
                name: "fill",
                formId,
                formTitle: form?.title,
              })
            }
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer"
          >
            <Mic className="w-3.5 h-3.5 text-neutral-800" />
            <span>Voice Fill Mode</span>
          </button>

          <button
            disabled={saving}
            onClick={handleSaveDraft}
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-neutral-400 rounded-lg text-xs font-medium text-neutral-700 transition-colors flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
          >
            <Save className="w-3.5 h-3.5" />
            <span>{saving ? "Saving..." : "Save Draft"}</span>
          </button>

          <button
            onClick={() =>
              setView({
                name: "review",
                formId,
                formTitle: form?.title,
                values,
              })
            }
            className="px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors flex items-center space-x-1.5 cursor-pointer shadow-xs"
          >
            <span>Review & Submit</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Form Completion Progress Card */}
      <div className="mt-6 p-4 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
        <div className="flex items-center space-x-3 flex-1 max-w-md">
          <span className="text-xs font-semibold text-neutral-900 whitespace-nowrap">
            Completion:
          </span>
          <div className="w-full bg-neutral-200 h-2 rounded-full overflow-hidden">
            <div
              className="bg-neutral-900 h-full transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <span className="text-xs font-bold text-neutral-900 font-mono">
            {progressPercent}%
          </span>
        </div>

        <div className="text-[11px] text-neutral-500 font-mono hidden sm:block">
          {filledRequiredCount} of {requiredFields.length} required fields filled
        </div>
      </div>

      {/* Main Form Fields */}
      <div className="mt-6 p-6 sm:p-8 bg-white border border-[#E5E5E5] rounded-2xl shadow-xs">
        <FormRenderer
          schema={form?.schema_json}
          values={values}
          onChange={setValues}
          errors={errors}
          aiFilledFields={aiFilledFields}
        />

        {/* Footer Actions */}
        <div className="mt-8 pt-5 border-t border-[#E5E5E5] flex items-center justify-between">
          <button
            type="button"
            onClick={() => {
              const reset = {};
              form?.schema_json?.fields?.forEach((f) => {
                reset[f.name] = f.type === "checkbox" ? false : "";
              });
              setValues(reset);
              toast("Reset all fields to blank.", "info");
            }}
            className="text-xs text-neutral-500 hover:text-black cursor-pointer"
          >
            Reset Form
          </button>

          <button
            type="button"
            onClick={() =>
              setView({
                name: "review",
                formId,
                formTitle: form?.title,
                values,
              })
            }
            className="px-5 py-2.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-all shadow-xs cursor-pointer flex items-center space-x-2"
          >
            <span>Proceed to Review</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
