import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  Save,
  Mic,
  Plus,
  Trash2,
  ChevronUp,
  ChevronDown,
  Eye,
  Sliders,
  Globe,
  Loader2,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";
import { useAuth } from "../context/AuthContext";
import FormRenderer, { normalizeBoolean } from "../components/forms/FormRenderer";

const SUPPORTED_CATEGORIES = [
  "General",
  "Education",
  "Careers",
  "Customer Experience",
  "Academic",
  "Financial Aid",
];

const FIELD_TYPES = [
  { value: "text", label: "Short Text" },
  { value: "textarea", label: "Multi-line Text (Textarea)" },
  { value: "number", label: "Numeric (Number)" },
  { value: "email", label: "Email Address" },
  { value: "phone", label: "Phone Number" },
  { value: "date", label: "Date" },
  { value: "time", label: "Time" },
  { value: "datetime", label: "Date & Time" },
  { value: "select", label: "Dropdown Menu (Select)" },
  { value: "radio", label: "Radio Buttons" },
  { value: "checkbox", label: "Checkbox (Boolean)" },
  { value: "url", label: "Website URL" },
];


export default function FormEditorPage({ formId, formTitle, setView }) {
  const { user } = useAuth();
  const { toast } = useToast();

  const [form, setForm] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Form Structure State
  const [activeTab, setActiveTab] = useState("fields"); // 'fields' | 'preview'
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("General");
  const [isPublic, setIsPublic] = useState(false);
  const [fields, setFields] = useState([]);

  // Preview State
  const [previewValues, setPreviewValues] = useState({});

  const isAdmin = user?.role === "ADMIN" || user?.role === "SUPER_ADMIN";

  useEffect(() => {
    let isMounted = true;
    const fetchForm = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await api.getForm(formId);
        if (!isMounted) return;
        setForm(data);
        setTitle(data.title || "");
        setDescription(data.description || "");
        setCategory(data.schema_json?.category || "General");
        setIsPublic(Boolean(data.is_public));

        const rawFields = data.schema_json?.fields || [];
        setFields(
          rawFields.map((f, i) => {
            const isCheckbox = f.type === "checkbox";
            const defVal = isCheckbox
              ? normalizeBoolean(f.default_value)
              : f.default_value !== undefined && f.default_value !== null
              ? f.default_value
              : "";
            return {
              id: f.id || `f_${f.name || i + 1}_${Date.now()}_${i}`,
              name: f.name || `field_${i + 1}`,
              label: f.label || `Field ${i + 1}`,
              type: f.type || "text",
              required: Boolean(f.required),
              placeholder: f.placeholder || "",
              description: f.description || "",
              default_value: defVal,
              options: Array.isArray(f.options) ? [...f.options] : [],
              min_value: f.min_value !== undefined && f.min_value !== null ? f.min_value : "",
              max_value: f.max_value !== undefined && f.max_value !== null ? f.max_value : "",
              step: f.step !== undefined && f.step !== null ? f.step : "",
              min_length: f.min_length !== undefined && f.min_length !== null ? f.min_length : "",
              max_length: f.max_length !== undefined && f.max_length !== null ? f.max_length : "",
              pattern: f.pattern || "",
            };
          })
        );
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

  // Field Reordering: Move Up
  const moveFieldUp = (index) => {
    if (index === 0) return;
    setFields((prev) => {
      const reordered = [...prev];
      const temp = reordered[index - 1];
      reordered[index - 1] = reordered[index];
      reordered[index] = temp;
      return reordered;
    });
  };

  // Field Reordering: Move Down
  const moveFieldDown = (index) => {
    if (index === fields.length - 1) return;
    setFields((prev) => {
      const reordered = [...prev];
      const temp = reordered[index + 1];
      reordered[index + 1] = reordered[index];
      reordered[index] = temp;
      return reordered;
    });
  };

  // Add Field
  const addField = () => {
    const idx = fields.length + 1;
    let baseName = `field_${idx}`;
    let counter = 1;
    const existingNames = new Set(fields.map((f) => f.name));
    while (existingNames.has(baseName)) {
      counter++;
      baseName = `field_${idx}_${counter}`;
    }

    const newField = {
      id: `field_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      name: baseName,
      label: `New Field ${idx}`,
      type: "text",
      required: false,
      placeholder: "",
      description: "",
      default_value: "",
      options: [],
      min_value: "",
      max_value: "",
      step: "",
      min_length: "",
      max_length: "",
      pattern: "",
    };

    setFields((prev) => [...prev, newField]);
  };

  // Delete Field
  const deleteField = (index) => {
    if (fields.length <= 1) {
      toast("A form must contain at least one field.", "info");
      return;
    }
    setFields((prev) => prev.filter((_, i) => i !== index));
  };

  // Update Field (Immutably)
  const updateField = (index, key, val) => {
    setFields((prev) =>
      prev.map((field, i) => {
        if (i !== index) return field;

        const updated = { ...field, [key]: val };

        // Handle field-type change with property preservation & cleanup
        if (key === "type") {
          if (["select", "radio"].includes(val)) {
            if (!updated.options || updated.options.length === 0) {
              updated.options = ["Option 1", "Option 2"];
            }
            if (!updated.options.includes(updated.default_value)) {
              updated.default_value = "";
            }
          } else {
            updated.options = [];
          }

          if (val === "checkbox") {
            updated.default_value = normalizeBoolean(updated.default_value);
          } else if (val === "number") {
            if (
              updated.default_value !== "" &&
              !isNaN(Number(updated.default_value)) &&
              isFinite(Number(updated.default_value))
            ) {
              updated.default_value = Number(updated.default_value);
            } else {
              updated.default_value = "";
            }
          } else if (typeof updated.default_value === "boolean") {
            updated.default_value = "";
          }

          if (val !== "number") {
            updated.min_value = "";
            updated.max_value = "";
            updated.step = "";
          }
          if (!["text", "textarea", "email", "phone", "url"].includes(val)) {
            updated.min_length = "";
            updated.max_length = "";
            updated.pattern = "";
          }
        }

        // Auto-suggest machine name if current name is empty
        if (key === "label" && !field.name) {
          const generated = val.toLowerCase().replace(/[^a-z0-9]/g, "_").slice(0, 32);
          if (generated) {
            updated.name = generated;
          }
        }

        return updated;
      })
    );
  };

  // Option list helper for select/radio
  const updateOption = (fieldIndex, optIndex, val) => {
    setFields((prev) =>
      prev.map((field, i) => {
        if (i !== fieldIndex) return field;
        const opts = [...(field.options || [])];
        const oldVal = opts[optIndex];
        opts[optIndex] = val;
        let newDefault = field.default_value;
        if (newDefault === oldVal) {
          newDefault = val;
        }
        return { ...field, options: opts, default_value: newDefault };
      })
    );
  };

  const addOption = (fieldIndex) => {
    setFields((prev) =>
      prev.map((field, i) => {
        if (i !== fieldIndex) return field;
        const opts = [...(field.options || [])];
        opts.push(`Option ${opts.length + 1}`);
        return { ...field, options: opts };
      })
    );
  };

  const removeOption = (fieldIndex, optIndex) => {
    setFields((prev) =>
      prev.map((field, i) => {
        if (i !== fieldIndex) return field;
        const opts = [...(field.options || [])];
        if (opts.length <= 1) {
          toast("Dropdown and radio fields must contain at least one option.", "info");
          return field;
        }
        const removedVal = opts[optIndex];
        opts.splice(optIndex, 1);
        let newDefault = field.default_value;
        if (newDefault === removedVal) {
          newDefault = "";
        }
        return { ...field, options: opts, default_value: newDefault };
      })
    );
  };

  const moveOptionUp = (fieldIndex, optIndex) => {
    if (optIndex === 0) return;
    setFields((prev) =>
      prev.map((field, i) => {
        if (i !== fieldIndex) return field;
        const opts = [...(field.options || [])];
        const temp = opts[optIndex - 1];
        opts[optIndex - 1] = opts[optIndex];
        opts[optIndex] = temp;
        return { ...field, options: opts };
      })
    );
  };

  const moveOptionDown = (fieldIndex, optIndex) => {
    setFields((prev) =>
      prev.map((field, i) => {
        if (i !== fieldIndex) return field;
        const opts = [...(field.options || [])];
        if (optIndex === opts.length - 1) return field;
        const temp = opts[optIndex + 1];
        opts[optIndex + 1] = opts[optIndex];
        opts[optIndex] = temp;
        return { ...field, options: opts };
      })
    );
  };

  // Save Form Handler
  const handleSaveForm = async (targetPublicState = null) => {
    if (saving) return;

    if (!title.trim()) {
      toast("Form title cannot be empty.", "error");
      return;
    }

    if (fields.length === 0) {
      toast("Please add at least one field before saving.", "error");
      return;
    }

    // Validate field labels, options, and constraints
    for (let i = 0; i < fields.length; i++) {
      const f = fields[i];
      if (!f.label.trim()) {
        toast(`Field #${i + 1} has an empty label. Please specify a label.`, "error");
        return;
      }
      if (["select", "radio"].includes(f.type)) {
        const cleanOpts = (f.options || []).map((o) => String(o).trim()).filter(Boolean);
        if (cleanOpts.length === 0) {
          toast(`Field "${f.label}" requires at least one valid option.`, "error");
          return;
        }
      }
      if (f.type === "number") {
        const minVal = f.min_value !== "" && f.min_value !== undefined ? Number(f.min_value) : null;
        const maxVal = f.max_value !== "" && f.max_value !== undefined ? Number(f.max_value) : null;
        const stepVal = f.step !== "" && f.step !== undefined ? Number(f.step) : null;

        if (minVal !== null && (!isFinite(minVal) || isNaN(minVal))) {
          toast(`Field "${f.label}": Minimum value must be a valid number.`, "error");
          return;
        }
        if (maxVal !== null && (!isFinite(maxVal) || isNaN(maxVal))) {
          toast(`Field "${f.label}": Maximum value must be a valid number.`, "error");
          return;
        }
        if (minVal !== null && maxVal !== null && minVal > maxVal) {
          toast(`Field "${f.label}": Minimum value (${minVal}) cannot exceed maximum value (${maxVal}).`, "error");
          return;
        }
        if (stepVal !== null && (stepVal <= 0 || !isFinite(stepVal) || isNaN(stepVal))) {
          toast(`Field "${f.label}": Step must be a positive number.`, "error");
          return;
        }
      }
      if (["text", "textarea", "email", "phone", "url"].includes(f.type)) {
        const minLen = f.min_length !== "" && f.min_length !== undefined ? Number(f.min_length) : null;
        const maxLen = f.max_length !== "" && f.max_length !== undefined ? Number(f.max_length) : null;

        if (minLen !== null && (minLen < 0 || isNaN(minLen))) {
          toast(`Field "${f.label}": Minimum length cannot be negative.`, "error");
          return;
        }
        if (maxLen !== null && (maxLen < 0 || isNaN(maxLen))) {
          toast(`Field "${f.label}": Maximum length cannot be negative.`, "error");
          return;
        }
        if (minLen !== null && maxLen !== null && minLen > maxLen) {
          toast(`Field "${f.label}": Minimum length cannot exceed maximum length.`, "error");
          return;
        }
        if (f.pattern && f.pattern.trim()) {
          try {
            new RegExp(f.pattern.trim());
          } catch {
            toast(`Field "${f.label}": Invalid regular expression pattern.`, "error");
            return;
          }
        }
      }
    }

    // De-duplicate field ids and names safely while preserving existing ids
    const seenIds = new Set();
    const seenNames = new Set();
    const cleanFields = fields.map((f, i) => {
      let fId = f.id || `f_${f.name || i + 1}_${Date.now()}`;
      if (seenIds.has(fId)) {
        let suffix = 2;
        while (seenIds.has(`${fId}_${suffix}`)) {
          suffix++;
        }
        fId = `${fId}_${suffix}`;
      }
      seenIds.add(fId);

      let fName = (f.name || `field_${i + 1}`)
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9_]/g, "_");
      if (!fName) fName = `field_${i + 1}`;

      if (seenNames.has(fName)) {
        let suffix = 2;
        while (seenNames.has(`${fName}_${suffix}`)) {
          suffix++;
        }
        fName = `${fName}_${suffix}`;
      }
      seenNames.add(fName);

      // Clean options for choice fields
      let cleanOpts = undefined;
      if (["select", "radio"].includes(f.type)) {
        const seenOpts = new Set();
        cleanOpts = [];
        for (const opt of f.options || []) {
          const s = String(opt).trim();
          if (s && !seenOpts.has(s)) {
            seenOpts.add(s);
            cleanOpts.push(s);
          }
        }
        if (cleanOpts.length === 0) {
          cleanOpts = ["Option 1", "Option 2"];
        }
      }

      // Safe default value calculation
      let defVal = undefined;
      if (f.default_value !== "" && f.default_value !== undefined && f.default_value !== null) {
        if (f.type === "checkbox") {
          defVal = normalizeBoolean(f.default_value);
        } else if (f.type === "number") {
          const num = Number(f.default_value);
          defVal = isFinite(num) && !isNaN(num) ? num : undefined;
        } else if (["select", "radio"].includes(f.type)) {
          defVal = cleanOpts && cleanOpts.includes(String(f.default_value).trim()) ? String(f.default_value).trim() : undefined;
        } else {
          defVal = String(f.default_value).trim() || undefined;
        }
      }

      const fieldObj = {
        id: fId,
        name: fName,
        label: f.label.trim(),
        type: f.type,
        required: Boolean(f.required),
        placeholder: f.placeholder?.trim() || undefined,
        description: f.description?.trim() || undefined,
        default_value: defVal,
        options: cleanOpts,
        min_value:
          f.type === "number" && f.min_value !== "" && isFinite(Number(f.min_value))
            ? Number(f.min_value)
            : undefined,
        max_value:
          f.type === "number" && f.max_value !== "" && isFinite(Number(f.max_value))
            ? Number(f.max_value)
            : undefined,
        step:
          f.type === "number" && f.step !== "" && isFinite(Number(f.step))
            ? Number(f.step)
            : undefined,
        min_length:
          ["text", "textarea", "email", "phone", "url"].includes(f.type) &&
          f.min_length !== "" &&
          !isNaN(Number(f.min_length))
            ? parseInt(f.min_length, 10)
            : undefined,
        max_length:
          ["text", "textarea", "email", "phone", "url"].includes(f.type) &&
          f.max_length !== "" &&
          !isNaN(Number(f.max_length))
            ? parseInt(f.max_length, 10)
            : undefined,
        pattern:
          ["text", "textarea", "email", "phone", "url"].includes(f.type) && f.pattern?.trim()
            ? f.pattern.trim()
            : undefined,
      };

      return fieldObj;
    });

    const finalIsPublic = targetPublicState !== null ? targetPublicState : isPublic;

    if (finalIsPublic && !isAdmin) {
      toast("Only administrators can publish forms publicly.", "error");
      return;
    }

    setSaving(true);
    try {
      const payload = {
        title: title.trim(),
        description: description.trim() || undefined,
        is_public: finalIsPublic,
        schema_json: {
          title: title.trim(),
          description: description.trim() || undefined,
          category: category || "General",
          fields: cleanFields,
        },
      };

      const updated = await api.updateForm(formId, payload);
      setForm(updated);
      setIsPublic(updated.is_public);
      setFields(
        (updated.schema_json?.fields || cleanFields).map((f) => ({
          ...f,
          id: f.id || `f_${f.name}`,
          placeholder: f.placeholder || "",
          description: f.description || "",
          default_value: f.default_value !== undefined && f.default_value !== null ? f.default_value : "",
          options: Array.isArray(f.options) ? [...f.options] : [],
          min_value: f.min_value !== undefined && f.min_value !== null ? f.min_value : "",
          max_value: f.max_value !== undefined && f.max_value !== null ? f.max_value : "",
          step: f.step !== undefined && f.step !== null ? f.step : "",
          min_length: f.min_length !== undefined && f.min_length !== null ? f.min_length : "",
          max_length: f.max_length !== undefined && f.max_length !== null ? f.max_length : "",
          pattern: f.pattern || "",
        }))
      );

      toast(
        finalIsPublic
          ? "Form published successfully! It is now accessible to all users."
          : "Form draft saved successfully.",
        "success"
      );
    } catch (err) {
      toast(`Failed to save form: ${err.message}`, "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto py-24 text-center">
        <div className="inline-block w-8 h-8 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin" />
        <p className="text-xs text-[#737373] mt-3 font-mono">Loading form editor...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto py-12 px-4">
        <div className="p-6 bg-red-50 border border-red-200 rounded-2xl text-red-700 text-sm">
          <p className="font-semibold">Unable to edit form</p>
          <p className="mt-1 text-xs">{error}</p>
          <button
            onClick={() => setView({ name: "dashboard" })}
            className="mt-4 px-3 py-1.5 bg-neutral-900 text-white rounded-lg text-xs font-semibold cursor-pointer"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  // Construct current preview schema object
  const previewSchema = {
    title: title || "Untitled Form",
    description: description || undefined,
    category: category || "General",
    fields: fields.map((f) => ({
      id: f.id,
      name: f.name,
      label: f.label || "Untitled Field",
      type: f.type,
      required: Boolean(f.required),
      placeholder: f.placeholder,
      description: f.description,
      default_value: f.default_value,
      options: f.options,
      min_value: f.min_value,
      max_value: f.max_value,
      step: f.step,
      min_length: f.min_length,
      max_length: f.max_length,
      pattern: f.pattern,
    })),
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-8 py-8 text-left">
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
          <div className="min-w-0">
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold tracking-tight text-neutral-900 break-words">
                {title || "Edit Form"}
              </h1>
              <span
                className={`text-[10px] font-mono px-2 py-0.5 rounded-full font-semibold border ${
                  isPublic
                    ? "bg-emerald-50 text-emerald-800 border-emerald-200"
                    : "bg-neutral-100 text-neutral-700 border-neutral-300"
                }`}
              >
                {isPublic ? "Published (Public)" : "Draft (Private)"}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full font-medium bg-neutral-100 text-neutral-600 border border-neutral-200">
                {category}
              </span>
            </div>
            <p className="text-xs text-[#737373] mt-0.5">
              Form Lifecycle Editor • Manage fields, validation, and publication status
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() =>
              setView({
                name: "fill",
                formId,
                formTitle: title,
              })
            }
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer"
          >
            <Mic className="w-3.5 h-3.5 text-neutral-800" />
            <span>Voice Fill</span>
          </button>

          <button
            disabled={saving}
            onClick={() => handleSaveForm(false)}
            className="px-3 py-1.5 border border-[#E5E5E5] hover:border-neutral-400 rounded-lg text-xs font-medium text-neutral-700 transition-colors flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
            title="Save changes while keeping form private as a draft"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            <span>Save Draft</span>
          </button>

          {isAdmin ? (
            <button
              disabled={saving}
              onClick={() => handleSaveForm(true)}
              className="px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors flex items-center space-x-1.5 cursor-pointer shadow-xs disabled:opacity-50"
              title="Publish form so all users can access and fill it"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Globe className="w-3.5 h-3.5" />}
              <span>{isPublic ? "Save & Keep Published" : "Publish to Dashboard"}</span>
            </button>
          ) : (
            <button
              disabled={saving}
              onClick={() => handleSaveForm(isPublic)}
              className="px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors flex items-center space-x-1.5 cursor-pointer shadow-xs disabled:opacity-50"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              <span>Save Changes</span>
            </button>
          )}
        </div>
      </div>

      {/* Tabs Switcher */}
      <div className="flex border-b border-[#E5E5E5] mt-6 gap-6 text-xs font-semibold">
        <button
          onClick={() => setActiveTab("fields")}
          className={`pb-3 cursor-pointer flex items-center space-x-1.5 transition-colors border-b-2 -mb-px ${
            activeTab === "fields"
              ? "border-neutral-900 text-neutral-900"
              : "border-transparent text-neutral-500 hover:text-neutral-900"
          }`}
        >
          <Sliders className="w-3.5 h-3.5" />
          <span>Fields & Validation ({fields.length})</span>
        </button>

        <button
          onClick={() => setActiveTab("preview")}
          className={`pb-3 cursor-pointer flex items-center space-x-1.5 transition-colors border-b-2 -mb-px ${
            activeTab === "preview"
              ? "border-neutral-900 text-neutral-900"
              : "border-transparent text-neutral-500 hover:text-neutral-900"
          }`}
        >
          <Eye className="w-3.5 h-3.5" />
          <span>Live Form Preview</span>
        </button>
      </div>

      {/* Tab 1: Fields & Schema Editor */}
      {activeTab === "fields" && (
        <div className="mt-6 space-y-6">
          {/* Metadata Card */}
          <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs space-y-4">
            <h3 className="text-xs font-semibold text-neutral-900 uppercase tracking-wider">
              Form Information & Visibility
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-1">
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Form Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Employee Registration Form"
                  className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Category
                </label>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                >
                  {!SUPPORTED_CATEGORIES.includes(category) && category && (
                    <option value={category}>{category}</option>
                  )}
                  {SUPPORTED_CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Visibility / Publication
                </label>
                <div className="flex items-center space-x-4 mt-2 text-xs">
                  <label className="inline-flex items-center space-x-2 cursor-pointer">
                    <input
                      type="radio"
                      name="is_public_radio"
                      checked={!isPublic}
                      onChange={() => setIsPublic(false)}
                      className="text-neutral-900 focus:ring-neutral-900"
                    />
                    <span className="text-neutral-800 font-medium">Draft (Private)</span>
                  </label>

                  <label
                    className={`inline-flex items-center space-x-2 ${
                      isAdmin ? "cursor-pointer" : "opacity-50 cursor-not-allowed"
                    }`}
                    title={isAdmin ? "" : "Only administrators can publish forms publicly"}
                  >
                    <input
                      type="radio"
                      name="is_public_radio"
                      disabled={!isAdmin}
                      checked={isPublic}
                      onChange={() => isAdmin && setIsPublic(true)}
                      className="text-neutral-900 focus:ring-neutral-900"
                    />
                    <span className="text-neutral-800 font-medium">Published (Public)</span>
                  </label>
                </div>
                {!isAdmin && (
                  <p className="text-[10px] text-neutral-400 mt-1">
                    * Administrator role required to publish templates to all users.
                  </p>
                )}
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-neutral-700 mb-1">
                Description
              </label>
              <textarea
                rows={2}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Brief summary of this form's purpose or instructions..."
                className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
              />
            </div>
          </div>

          {/* Fields List */}
          <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#E5E5E5]">
              <div>
                <h3 className="text-xs font-semibold text-neutral-900 uppercase tracking-wider">
                  Configured Form Fields ({fields.length})
                </h3>
                <p className="text-[11px] text-[#737373] mt-0.5">
                  Reorder, customize validation rules, and configure field options safely.
                </p>
              </div>

              <button
                type="button"
                onClick={addField}
                className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer shadow-xs"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Field</span>
              </button>
            </div>

            <div className="space-y-4 pt-2">
              {fields.map((field, idx) => (
                <div
                  key={field.id || `field_${idx}`}
                  className="p-4 border border-[#E5E5E5] rounded-xl bg-white hover:border-neutral-300 transition-colors space-y-3.5"
                >
                  {/* Top Bar of Field */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="font-mono text-xs font-bold text-neutral-800">
                        #{idx + 1}
                      </span>
                      <span className="text-xs font-semibold text-neutral-900">
                        {field.label || "Untitled Field"}
                      </span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-600">
                        type: {field.type}
                      </span>
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-600">
                        key: {field.name}
                      </span>
                    </div>

                    <div className="flex items-center space-x-1">
                      {/* Move Up */}
                      <button
                        type="button"
                        disabled={idx === 0}
                        onClick={() => moveFieldUp(idx)}
                        className="p-1 rounded text-neutral-500 hover:text-black hover:bg-neutral-100 transition-colors disabled:opacity-30 cursor-pointer"
                        title="Move Up"
                      >
                        <ChevronUp className="w-4 h-4" />
                      </button>

                      {/* Move Down */}
                      <button
                        type="button"
                        disabled={idx === fields.length - 1}
                        onClick={() => moveFieldDown(idx)}
                        className="p-1 rounded text-neutral-500 hover:text-black hover:bg-neutral-100 transition-colors disabled:opacity-30 cursor-pointer"
                        title="Move Down"
                      >
                        <ChevronDown className="w-4 h-4" />
                      </button>

                      {/* Delete */}
                      <button
                        type="button"
                        onClick={() => deleteField(idx)}
                        className="p-1 rounded text-neutral-400 hover:text-red-600 hover:bg-red-50 transition-colors cursor-pointer ml-1"
                        title="Delete Field"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>

                  {/* Primary Config Row: Label, Type, Placeholder */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div>
                      <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                        Field Label <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={field.label}
                        onChange={(e) => updateField(idx, "label", e.target.value)}
                        placeholder="e.g. Email Address"
                        className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                        Field Type
                      </label>
                      <select
                        value={field.type}
                        onChange={(e) => updateField(idx, "type", e.target.value)}
                        className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                      >
                        {FIELD_TYPES.map((ft) => (
                          <option key={ft.value} value={ft.value}>
                            {ft.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                        Placeholder / Hint
                      </label>
                      <input
                        type="text"
                        value={field.placeholder || ""}
                        onChange={(e) => updateField(idx, "placeholder", e.target.value)}
                        placeholder="e.g. Enter legal name"
                        className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                      />
                    </div>
                  </div>

                  {/* Secondary Config Row: Description & Default Value */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                        Help Text / Description (Optional)
                      </label>
                      <input
                        type="text"
                        value={field.description || ""}
                        onChange={(e) => updateField(idx, "description", e.target.value)}
                        placeholder="e.g. Enter with country code (+1)"
                        className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                        Default Value (Optional)
                      </label>
                      {field.type === "checkbox" ? (
                        <div className="flex items-center space-x-2 pt-1.5">
                          <input
                            type="checkbox"
                            checked={normalizeBoolean(field.default_value)}
                            onChange={(e) => updateField(idx, "default_value", e.target.checked)}
                            className="w-4 h-4 rounded border-[#E5E5E5] text-neutral-900 focus:ring-neutral-900 cursor-pointer"
                          />
                          <span className="text-xs text-neutral-700">Checked by default</span>
                        </div>
                      ) : ["select", "radio"].includes(field.type) ? (
                        <select
                          value={field.default_value || ""}
                          onChange={(e) => updateField(idx, "default_value", e.target.value)}
                          className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                        >
                          <option value="">-- No Default Selected --</option>
                          {(field.options || []).map((opt, optIdx) => (
                            <option key={optIdx} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      ) : field.type === "number" ? (
                        <input
                          type="number"
                          value={field.default_value || ""}
                          onChange={(e) => updateField(idx, "default_value", e.target.value)}
                          placeholder="e.g. 0"
                          className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                        />
                      ) : field.type === "date" ? (
                        <input
                          type="date"
                          value={field.default_value || ""}
                          onChange={(e) => updateField(idx, "default_value", e.target.value)}
                          className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                        />
                      ) : field.type === "time" ? (
                        <input
                          type="time"
                          value={field.default_value || ""}
                          onChange={(e) => updateField(idx, "default_value", e.target.value)}
                          className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                        />
                      ) : field.type === "datetime" ? (
                        <input
                          type="datetime-local"
                          value={field.default_value || ""}
                          onChange={(e) => updateField(idx, "default_value", e.target.value)}
                          className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                        />
                      ) : (
                        <input
                          type="text"
                          value={field.default_value || ""}
                          onChange={(e) => updateField(idx, "default_value", e.target.value)}
                          placeholder="Initial value"
                          className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                        />
                      )}
                    </div>
                  </div>

                  {/* Type-Specific Options Manager (select / radio) */}
                  {["select", "radio"].includes(field.type) && (
                    <div className="p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-lg space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold text-neutral-700">
                          Options for {field.type === "select" ? "Dropdown" : "Radio Buttons"} ({field.options?.length || 0})
                        </span>
                        <button
                          type="button"
                          onClick={() => addOption(idx)}
                          className="text-[11px] text-neutral-900 hover:underline flex items-center space-x-1 cursor-pointer font-medium"
                        >
                          <Plus className="w-3 h-3" />
                          <span>Add Option</span>
                        </button>
                      </div>

                      <div className="space-y-1.5">
                        {(field.options || []).map((opt, optIdx) => (
                          <div key={optIdx} className="flex items-center space-x-1.5">
                            <span className="text-[10px] font-mono text-neutral-400 w-4 text-center">
                              {optIdx + 1}
                            </span>
                            <input
                              type="text"
                              value={opt}
                              onChange={(e) => updateOption(idx, optIdx, e.target.value)}
                              placeholder={`Option ${optIdx + 1}`}
                              className="w-full px-2 py-1 text-xs border border-[#E5E5E5] rounded bg-white focus:outline-none focus:border-neutral-900"
                            />
                            <button
                              type="button"
                              disabled={optIdx === 0}
                              onClick={() => moveOptionUp(idx, optIdx)}
                              className="p-1 rounded text-neutral-400 hover:text-black disabled:opacity-20 cursor-pointer"
                              title="Move option up"
                            >
                              <ChevronUp className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              disabled={optIdx === (field.options?.length || 0) - 1}
                              onClick={() => moveOptionDown(idx, optIdx)}
                              className="p-1 rounded text-neutral-400 hover:text-black disabled:opacity-20 cursor-pointer"
                              title="Move option down"
                            >
                              <ChevronDown className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              onClick={() => removeOption(idx, optIdx)}
                              className="text-neutral-400 hover:text-red-600 p-1 cursor-pointer"
                              title="Remove option"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Type-Specific Constraints: Number (Min, Max, Step) */}
                  {field.type === "number" && (
                    <div className="p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-lg">
                      <span className="block text-[11px] font-semibold text-neutral-700 mb-2">
                        Numeric Constraints (Optional)
                      </span>
                      <div className="grid grid-cols-3 gap-3">
                        <div>
                          <label className="block text-[10px] text-neutral-500 mb-0.5">Min Value</label>
                          <input
                            type="number"
                            value={field.min_value !== undefined ? field.min_value : ""}
                            onChange={(e) => updateField(idx, "min_value", e.target.value)}
                            placeholder="e.g. 0"
                            className="w-full px-2 py-1 text-xs border border-[#E5E5E5] rounded bg-white focus:outline-none focus:border-neutral-900"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-neutral-500 mb-0.5">Max Value</label>
                          <input
                            type="number"
                            value={field.max_value !== undefined ? field.max_value : ""}
                            onChange={(e) => updateField(idx, "max_value", e.target.value)}
                            placeholder="e.g. 100"
                            className="w-full px-2 py-1 text-xs border border-[#E5E5E5] rounded bg-white focus:outline-none focus:border-neutral-900"
                          />
                        </div>
                        <div>
                          <label className="block text-[10px] text-neutral-500 mb-0.5">Step</label>
                          <input
                            type="number"
                            value={field.step !== undefined ? field.step : ""}
                            onChange={(e) => updateField(idx, "step", e.target.value)}
                            placeholder="e.g. 1 or 0.1"
                            className="w-full px-2 py-1 text-xs border border-[#E5E5E5] rounded bg-white focus:outline-none focus:border-neutral-900"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Type-Specific Constraints: Text / Textarea / Email / Phone / URL */}
                  {["text", "textarea", "email", "phone", "url"].includes(field.type) && (
                    <div className="p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-lg">
                      <span className="block text-[11px] font-semibold text-neutral-700 mb-2">
                        Text & Validation Constraints (Optional)
                      </span>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        {["text", "textarea"].includes(field.type) && (
                          <>
                            <div>
                              <label className="block text-[10px] text-neutral-500 mb-0.5">Min Characters</label>
                              <input
                                type="number"
                                min="0"
                                value={field.min_length !== undefined ? field.min_length : ""}
                                onChange={(e) => updateField(idx, "min_length", e.target.value)}
                                placeholder="e.g. 2"
                                className="w-full px-2 py-1 text-xs border border-[#E5E5E5] rounded bg-white focus:outline-none focus:border-neutral-900"
                              />
                            </div>
                            <div>
                              <label className="block text-[10px] text-neutral-500 mb-0.5">Max Characters</label>
                              <input
                                type="number"
                                min="1"
                                value={field.max_length !== undefined ? field.max_length : ""}
                                onChange={(e) => updateField(idx, "max_length", e.target.value)}
                                placeholder="e.g. 500"
                                className="w-full px-2 py-1 text-xs border border-[#E5E5E5] rounded bg-white focus:outline-none focus:border-neutral-900"
                              />
                            </div>
                          </>
                        )}
                        <div className={["text", "textarea"].includes(field.type) ? "" : "md:col-span-3"}>
                          <label className="block text-[10px] text-neutral-500 mb-0.5">Regex Pattern</label>
                          <input
                            type="text"
                            value={field.pattern || ""}
                            onChange={(e) => updateField(idx, "pattern", e.target.value)}
                            placeholder="e.g. ^[A-Za-z0-9_-]+$"
                            className="w-full px-2 py-1 text-xs border border-[#E5E5E5] rounded bg-white focus:outline-none focus:border-neutral-900 font-mono text-[11px]"
                          />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Bottom Row of Field: Required & Schema Key */}
                  <div className="pt-2 flex flex-wrap items-center justify-between border-t border-neutral-100 text-xs gap-2">
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={field.required}
                        onChange={(e) => updateField(idx, "required", e.target.checked)}
                        className="w-3.5 h-3.5 rounded border-[#E5E5E5] text-neutral-900 focus:ring-neutral-900"
                      />
                      <span className="text-neutral-700 font-medium">Required field</span>
                    </label>

                    <div className="flex items-center space-x-1.5 text-[11px] text-neutral-400 font-mono">
                      <span>Field Key:</span>
                      <input
                        type="text"
                        value={field.name}
                        onChange={(e) =>
                          updateField(
                            idx,
                            "name",
                            e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_")
                          )
                        }
                        placeholder="field_key"
                        className="px-2 py-0.5 border border-[#E5E5E5] rounded font-mono text-[11px] text-neutral-700 focus:outline-none focus:border-neutral-900 bg-white"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Bottom Actions */}
            <div className="pt-6 border-t border-[#E5E5E5] flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                onClick={addField}
                className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1 cursor-pointer"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>Add Another Field</span>
              </button>

              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => handleSaveForm(false)}
                  className="px-4 py-2 border border-[#E5E5E5] hover:border-neutral-400 rounded-lg text-xs font-semibold text-neutral-800 transition-colors cursor-pointer disabled:opacity-50"
                >
                  Save as Draft
                </button>

                {isAdmin ? (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => handleSaveForm(true)}
                    className="px-5 py-2 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors shadow-xs cursor-pointer flex items-center space-x-1.5 disabled:opacity-50"
                  >
                    {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    <span>{isPublic ? "Save Changes" : "Publish Form"}</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    disabled={saving}
                    onClick={() => handleSaveForm(isPublic)}
                    className="px-5 py-2 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors shadow-xs cursor-pointer flex items-center space-x-1.5 disabled:opacity-50"
                  >
                    {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                    <span>Save Changes</span>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tab 2: Live Form Preview */}
      {activeTab === "preview" && (
        <div className="mt-6 space-y-6">
          <div className="bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl p-4 flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold text-neutral-900">
                Interactive Preview Mode
              </p>
              <p className="text-[11px] text-[#737373]">
                Test how users will interact with this form during manual entry or voice filling.
              </p>
            </div>
            <button
              onClick={() => setActiveTab("fields")}
              className="px-3 py-1.5 bg-white border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors cursor-pointer"
            >
              Back to Structure Editor
            </button>
          </div>

          <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 sm:p-8 shadow-xs">
            <FormRenderer
              schema={previewSchema}
              values={previewValues}
              onChange={setPreviewValues}
              errors={{}}
            />
          </div>
        </div>
      )}
    </div>
  );
}
