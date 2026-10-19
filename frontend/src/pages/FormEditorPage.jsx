import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  Save,
  Mic,
  ArrowRight,
  Sparkles,
  AlertCircle,
  Plus,
  Trash2,
  ChevronUp,
  ChevronDown,
  Eye,
  Sliders,
  CheckCircle2,
  Globe,
  Lock,
  Loader2,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";
import { useAuth } from "../context/AuthContext";
import FormRenderer from "../components/forms/FormRenderer";

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
        setIsPublic(Boolean(data.is_public));

        const rawFields = data.schema_json?.fields || [];
        setFields(
          rawFields.map((f, i) => ({
            name: f.name || `field_${i + 1}`,
            label: f.label || `Field ${i + 1}`,
            type: f.type || "text",
            required: Boolean(f.required),
            placeholder: f.placeholder || "",
            options: Array.isArray(f.options) ? [...f.options] : [],
          }))
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
    const reordered = [...fields];
    const temp = reordered[index - 1];
    reordered[index - 1] = reordered[index];
    reordered[index] = temp;
    setFields(reordered);
  };

  // Field Reordering: Move Down
  const moveFieldDown = (index) => {
    if (index === fields.length - 1) return;
    const reordered = [...fields];
    const temp = reordered[index + 1];
    reordered[index + 1] = reordered[index];
    reordered[index] = temp;
    setFields(reordered);
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

    setFields([
      ...fields,
      {
        name: baseName,
        label: `New Field ${idx}`,
        type: "text",
        required: false,
        placeholder: "",
        options: [],
      },
    ]);
  };

  // Delete Field
  const deleteField = (index) => {
    if (fields.length <= 1) {
      toast("A form must contain at least one field.", "info");
      return;
    }
    setFields(fields.filter((_, i) => i !== index));
  };

  // Update Field
  const updateField = (index, key, val) => {
    const updated = [...fields];
    updated[index][key] = val;

    // Auto-update field name if user edits label on generic name
    if (key === "label" && (!updated[index].name || updated[index].name.startsWith("field_") || updated[index].name.startsWith("custom_field_"))) {
      const generated = val.toLowerCase().replace(/[^a-z0-9]/g, "_").slice(0, 32);
      if (generated) {
        updated[index].name = generated;
      }
    }

    // Default options if switching to select/radio
    if (key === "type" && ["select", "radio"].includes(val) && (!updated[index].options || updated[index].options.length === 0)) {
      updated[index].options = ["Option 1", "Option 2"];
    }

    setFields(updated);
  };

  // Option list helper for select/radio
  const updateOption = (fieldIndex, optIndex, val) => {
    const updated = [...fields];
    const opts = [...(updated[fieldIndex].options || [])];
    opts[optIndex] = val;
    updated[fieldIndex].options = opts;
    setFields(updated);
  };

  const addOption = (fieldIndex) => {
    const updated = [...fields];
    const opts = [...(updated[fieldIndex].options || [])];
    opts.push(`Option ${opts.length + 1}`);
    updated[fieldIndex].options = opts;
    setFields(updated);
  };

  const removeOption = (fieldIndex, optIndex) => {
    const updated = [...fields];
    const opts = [...(updated[fieldIndex].options || [])];
    if (opts.length <= 1) {
      toast("Dropdown/radio fields must have at least one option.", "info");
      return;
    }
    opts.splice(optIndex, 1);
    updated[fieldIndex].options = opts;
    setFields(updated);
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

    // Validate field labels
    for (let i = 0; i < fields.length; i++) {
      if (!fields[i].label.trim()) {
        toast(`Field #${i + 1} has an empty label. Please specify a label.`, "error");
        return;
      }
    }

    // De-duplicate field names
    const seenNames = new Set();
    const cleanFields = fields.map((f, i) => {
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

      return {
        name: fName,
        label: f.label.trim(),
        type: f.type,
        required: Boolean(f.required),
        placeholder: f.placeholder ? f.placeholder.trim() : undefined,
        options: ["select", "radio"].includes(f.type)
          ? f.options && f.options.length > 0
            ? f.options
            : ["Option 1", "Option 2"]
          : undefined,
      };
    });

    const finalIsPublic = targetPublicState !== null ? targetPublicState : isPublic;

    // Check admin permission for publishing
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
          fields: cleanFields,
        },
      };

      const updated = await api.updateForm(formId, payload);
      setForm(updated);
      setIsPublic(updated.is_public);
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
    fields: fields.map((f, i) => ({
      name: f.name || `field_${i + 1}`,
      label: f.label || `Field ${i + 1}`,
      type: f.type,
      required: Boolean(f.required),
      placeholder: f.placeholder,
      options: f.options,
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

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
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
                  Order, validation types, and options are preserved upon saving.
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
                  key={idx}
                  className="p-4 border border-[#E5E5E5] rounded-xl bg-white hover:border-neutral-300 transition-colors space-y-3"
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

                  {/* Config Inputs */}
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
                        <option value="text">Text</option>
                        <option value="email">Email Address</option>
                        <option value="number">Numeric</option>
                        <option value="date">Date</option>
                        <option value="time">Time</option>
                        <option value="textarea">Multi-line Text (Textarea)</option>
                        <option value="select">Dropdown Menu (Select)</option>
                        <option value="radio">Radio Buttons</option>
                        <option value="checkbox">Checkbox (Boolean)</option>
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
                        placeholder="e.g. Enter full legal name"
                        className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 bg-white"
                      />
                    </div>
                  </div>

                  {/* Options Manager for select/radio */}
                  {["select", "radio"].includes(field.type) && (
                    <div className="p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-lg space-y-2">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] font-semibold text-neutral-700">
                          Options for {field.type === "select" ? "Dropdown" : "Radio"}
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
                          <div key={optIdx} className="flex items-center space-x-2">
                            <input
                              type="text"
                              value={opt}
                              onChange={(e) => updateOption(idx, optIdx, e.target.value)}
                              placeholder={`Option ${optIdx + 1}`}
                              className="w-full px-2 py-1 text-xs border border-[#E5E5E5] rounded bg-white focus:outline-none focus:border-neutral-900"
                            />
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

                  {/* Bottom Row of Field: Required & Schema Key */}
                  <div className="pt-2 flex items-center justify-between border-t border-neutral-100 text-xs">
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={field.required}
                        onChange={(e) => updateField(idx, "required", e.target.checked)}
                        className="w-3.5 h-3.5 rounded border-[#E5E5E5] text-neutral-900 focus:ring-neutral-900"
                      />
                      <span className="text-neutral-700 font-medium">Required field</span>
                    </label>

                    <div className="flex items-center space-x-1 text-[11px] text-neutral-400 font-mono">
                      <span>Field key:</span>
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
                        className="px-1.5 py-0.5 border border-[#E5E5E5] rounded font-mono text-[11px] text-neutral-700 focus:outline-none focus:border-neutral-900"
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
