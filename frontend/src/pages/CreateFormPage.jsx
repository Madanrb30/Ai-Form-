import React, { useState, useRef } from "react";
import {
  Upload,
  Layers,
  FilePlus,
  ArrowLeft,
  Sparkles,
  AlertCircle,
  FileText,
  Trash2,
  Plus,
  ArrowRight,
  Loader2,
  X,
  Edit3,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";
import FormRenderer from "../components/forms/FormRenderer";

const TEMPLATES = [
  {
    id: "student-reg",
    title: "Student Registration Form",
    category: "Education",
    description: "Standard university admission form collecting student credentials, academic department, and personal contact info.",
    prompt: "Create a student registration form containing full name, register number, department, email address, phone number, date of birth, and gender.",
  },
  {
    id: "job-app",
    title: "Job Application Form",
    category: "Careers",
    description: "Candidate onboarding form capturing target position, total years of experience, contact details, and portfolio link.",
    prompt: "Create a job application form with candidate name, email, phone number, target position, years of experience, available start date, and cover letter.",
  },
  {
    id: "feedback",
    title: "Customer Feedback Survey",
    category: "Customer Experience",
    description: "Evaluates client satisfaction, rating, specific services used, feedback remarks, and recommendation likelihood.",
    prompt: "Create a customer feedback survey with name, email, satisfaction rating, service used, would recommend checkbox, and detailed comments.",
  },
  {
    id: "college-adm",
    title: "College Admission Form",
    category: "Academic",
    description: "Detailed college admission form covering high school score, chosen stream, guardian contact, and residential address.",
    prompt: "Create a college admission form with student full name, high school GPA, chosen stream, parent or guardian name, phone number, address, and date of birth.",
  },
  {
    id: "scholarship",
    title: "Scholarship Application",
    category: "Financial Aid",
    description: "Application capturing household income, academic merit, field of study, and statement of financial purpose.",
    prompt: "Create a scholarship application form with applicant name, current college, major, cumulative GPA, annual family income, statement of purpose, and email address.",
  },
  {
    id: "contact-info",
    title: "Contact Information Form",
    category: "General",
    description: "Essential contact directory form gathering full legal name, preferred contact method, mobile number, and city.",
    prompt: "Create a contact information form with full name, email address, mobile number, city, preferred contact method, and message notes.",
  },
];

export default function CreateFormPage({ setView }) {
  const { toast } = useToast();
  const [activeTab, setActiveTab] = useState("upload"); // 'upload' | 'template' | 'blank'

  // --- Upload State ---
  const [file, setFile] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadError, setUploadError] = useState(null);
  const [analyzingFile, setAnalyzingFile] = useState(false);
  const fileInputRef = useRef(null);

  // --- Template State ---
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [generatingTemplate, setGeneratingTemplate] = useState(false);

  // --- Blank Form State ---
  const [blankTitle, setBlankTitle] = useState("");
  const [blankDesc, setBlankDesc] = useState("");
  const [blankFields, setBlankFields] = useState([
    { name: "full_name", label: "Full Name", type: "text", required: true, placeholder: "e.g. John Doe", options: [] },
    { name: "email", label: "Email Address", type: "email", required: true, placeholder: "name@example.com", options: [] },
    { name: "phone_number", label: "Phone Number", type: "text", required: false, placeholder: "10-digit mobile number", options: [] },
  ]);
  const [savingBlank, setSavingBlank] = useState(false);

  // --- Generated Preview State ---
  const [generatedSchema, setGeneratedSchema] = useState(null);
  const [extractionMeta, setExtractionMeta] = useState(null);
  const [previewMode, setPreviewMode] = useState("preview"); // 'preview' | 'edit'
  const [savingSchema, setSavingSchema] = useState(false);

  // --- Drag and Drop Handlers ---
  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelected = (selectedFile) => {
    setUploadError(null);
    setUploadProgress(0);

    // Validate type
    const validExtensions = [".pdf", ".png", ".jpg", ".jpeg"];
    const fileName = selectedFile.name.toLowerCase();
    const isValid = validExtensions.some((ext) => fileName.endsWith(ext));

    if (!isValid) {
      setUploadError("Unsupported file type. Please upload a PDF, PNG, or JPG document.");
      return;
    }

    // Validate size (15 MB)
    if (selectedFile.size > 15 * 1024 * 1024) {
      setUploadError("File exceeds the maximum 15MB limit.");
      return;
    }

    setFile(selectedFile);

    // Simulate progress
    let progress = 0;
    const interval = setInterval(() => {
      progress += 25;
      setUploadProgress(progress);
      if (progress >= 100) {
        clearInterval(interval);
      }
    }, 70);
  };

  const handleAnalyzeUploadedFile = async () => {
    if (!file || analyzingFile) return;
    setAnalyzingFile(true);
    setUploadError(null);

    try {
      // Send document to backend hybrid pipeline (Digital PDF / Scanned PDF Vision / Image OCR)
      const res = await api.uploadDocument(file);
      setGeneratedSchema(res.schema_data);
      setExtractionMeta(res);

      const strategyLabel =
        res.extraction_strategy === "groq_vision"
          ? "Groq Vision OCR"
          : res.extraction_strategy === "hybrid"
          ? "Hybrid OCR & Text"
          : res.extraction_strategy === "acroform"
          ? "Interactive AcroForm"
          : "Digital PDF Text";

      toast(
        `${strategyLabel}: ${res.detected_fields_count} field(s) extracted!`,
        "success"
      );
    } catch (err) {
      setUploadError(`Document extraction failed: ${err.message}`);
      toast(`Document extraction error: ${err.message}`, "error");
    } finally {
      setAnalyzingFile(false);
    }
  };

  // --- Template Selection Handler ---
  const handleSelectTemplate = async (tmpl) => {
    setSelectedTemplate(tmpl);
    setGeneratingTemplate(true);
    try {
      const res = await api.generateForm(tmpl.prompt);
      setGeneratedSchema(res.schema_data);
      toast(`Loaded schema for ${tmpl.title}`, "success");
    } catch (err) {
      toast(`Error loading template: ${err.message}`, "error");
    } finally {
      setGeneratingTemplate(false);
    }
  };

  // --- Save Generated Form to Backend ---
  const handleSaveToDatabase = async () => {
    if (!generatedSchema) return;
    setSavingSchema(true);
    try {
      const created = await api.createForm({
        title: generatedSchema.title,
        description: generatedSchema.description,
        schema_json: generatedSchema,
      });
      toast("Form saved successfully to SQLite database!", "success");
      // Direct user to Voice Assistant page for this new form!
      setView({
        name: "fill",
        formId: created.id,
        formTitle: created.title,
      });
    } catch (err) {
      toast(`Failed to save form: ${err.message}`, "error");
    } finally {
      setSavingSchema(false);
    }
  };

  // --- Blank Form Field Management ---
  const addBlankField = () => {
    const idx = blankFields.length + 1;
    setBlankFields([
      ...blankFields,
      {
        name: `custom_field_${idx}`,
        label: `New Field ${idx}`,
        type: "text",
        required: false,
        placeholder: "Enter value",
        options: [],
      },
    ]);
  };

  const removeBlankField = (index) => {
    if (blankFields.length <= 1) {
      toast("A form must have at least one field.", "info");
      return;
    }
    setBlankFields(blankFields.filter((_, i) => i !== index));
  };

  const updateBlankField = (index, key, val) => {
    const updated = [...blankFields];
    updated[index][key] = val;
    if (key === "label" && (!updated[index].name || updated[index].name.startsWith("custom_field_"))) {
      updated[index].name = val.toLowerCase().replace(/[^a-z0-9]/g, "_").slice(0, 32);
    }
    setBlankFields(updated);
  };

  const handleSaveBlankForm = async (e) => {
    e.preventDefault();
    if (!blankTitle.trim()) {
      toast("Please provide a title for your form.", "error");
      return;
    }
    setSavingBlank(true);
    try {
      const schemaJson = {
        title: blankTitle.trim(),
        description: blankDesc.trim() || undefined,
        fields: blankFields.map((f) => ({
          name: f.name.trim().toLowerCase().replace(/[^a-z0-9_]/g, "_") || "field",
          label: f.label.trim() || "Field",
          type: f.type,
          required: Boolean(f.required),
          placeholder: f.placeholder || undefined,
          options: ["select", "radio"].includes(f.type)
            ? f.options.length > 0
              ? f.options
              : ["Option 1", "Option 2"]
            : undefined,
        })),
      };

      const created = await api.createForm({
        title: blankTitle.trim(),
        description: blankDesc.trim() || undefined,
        schema_json: schemaJson,
      });

      toast("Blank form created successfully!", "success");
      setView({
        name: "fill",
        formId: created.id,
        formTitle: created.title,
      });
    } catch (err) {
      toast(`Failed to create form: ${err.message}`, "error");
    } finally {
      setSavingBlank(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-8 py-8 text-left">
      {/* Header & Back Action */}
      <div className="flex items-center space-x-3 pb-6 border-b border-[#E5E5E5]">
        <button
          onClick={() => setView({ name: "dashboard" })}
          className="p-1.5 rounded-lg border border-[#E5E5E5] hover:bg-neutral-100 text-neutral-600 hover:text-black transition-colors cursor-pointer"
          title="Back to Dashboard"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h1 className="text-xl font-bold tracking-tight text-neutral-900">
            Create a New Form
          </h1>
          <p className="text-xs text-[#737373] mt-0.5">
            Upload a document, choose from curated templates, or build from blank.
          </p>
        </div>
      </div>

      {/* Tabs Switcher */}
      <div className="flex border-b border-[#E5E5E5] mt-6">
        <button
          onClick={() => {
            setActiveTab("upload");
            setGeneratedSchema(null);
          }}
          className={`flex items-center space-x-2 py-3 px-4 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
            activeTab === "upload"
              ? "border-neutral-900 text-neutral-900"
              : "border-transparent text-neutral-400 hover:text-neutral-700"
          }`}
        >
          <Upload className="w-3.5 h-3.5" />
          <span>Upload Form</span>
        </button>

        <button
          onClick={() => {
            setActiveTab("template");
            setGeneratedSchema(null);
          }}
          className={`flex items-center space-x-2 py-3 px-4 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
            activeTab === "template"
              ? "border-neutral-900 text-neutral-900"
              : "border-transparent text-neutral-400 hover:text-neutral-700"
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>From Template</span>
        </button>

        <button
          onClick={() => {
            setActiveTab("blank");
            setGeneratedSchema(null);
          }}
          className={`flex items-center space-x-2 py-3 px-4 text-xs font-semibold border-b-2 transition-all cursor-pointer ${
            activeTab === "blank"
              ? "border-neutral-900 text-neutral-900"
              : "border-transparent text-neutral-400 hover:text-neutral-700"
          }`}
        >
          <FilePlus className="w-3.5 h-3.5" />
          <span>Blank Form</span>
        </button>
      </div>

      {/* TAB 1: UPLOAD FORM */}
      {activeTab === "upload" && !generatedSchema && (
        <div className="mt-8 space-y-6">
          {/* Dropzone */}
          <div
            onDragOver={handleDragOver}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-[#E5E5E5] hover:border-neutral-900 rounded-2xl bg-[#F7F7F7] p-10 text-center cursor-pointer transition-all hover:bg-neutral-50/50"
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={(e) => e.target.files?.[0] && handleFileSelected(e.target.files[0])}
              accept=".pdf,.png,.jpg,.jpeg"
              className="hidden"
            />
            <div className="w-12 h-12 rounded-xl bg-white border border-[#E5E5E5] flex items-center justify-center mx-auto mb-3 shadow-xs">
              <Upload className="w-5 h-5 text-neutral-800" />
            </div>
            <p className="text-xs font-semibold text-neutral-900">
              Click to browse or drag and drop your document
            </p>
            <p className="text-[11px] text-[#737373] mt-1">
              Supports PDF, PNG, JPG/JPEG (Maximum 10 MB)
            </p>
          </div>

          {/* Validation Error with Retry & Manual Fallback */}
          {uploadError && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl space-y-3">
              <div className="flex items-start space-x-2 text-xs text-red-700">
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
                <span className="font-medium">{uploadError}</span>
              </div>
              <div className="flex items-center space-x-3 pt-1">
                <button
                  type="button"
                  onClick={handleAnalyzeUploadedFile}
                  disabled={analyzingFile}
                  className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-red-700 hover:bg-red-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Retry Extraction</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab("blank")}
                  className="px-3 py-1.5 bg-white border border-red-300 hover:bg-red-50 text-red-700 rounded-lg text-xs font-medium transition-colors cursor-pointer"
                >
                  Switch to Manual Entry
                </button>
              </div>
            </div>
          )}

          {/* Uploaded File Item Preview */}
          {file && (
            <div className="p-4 border border-[#E5E5E5] rounded-xl bg-white shadow-xs">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-3 min-w-0">
                  <div className="w-8 h-8 rounded-lg bg-neutral-100 flex items-center justify-center shrink-0">
                    <FileText className="w-4 h-4 text-neutral-700" />
                  </div>
                  <div className="truncate">
                    <p className="text-xs font-semibold text-neutral-900 truncate">
                      {file.name}
                    </p>
                    <p className="text-[11px] text-neutral-500 font-mono">
                      {(file.size / 1024).toFixed(1)} KB • Ready for extraction
                    </p>
                  </div>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                    setUploadProgress(0);
                  }}
                  className="p-1 text-neutral-400 hover:text-neutral-900 rounded cursor-pointer"
                  title="Remove file"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Progress bar */}
              <div className="w-full bg-neutral-100 h-1.5 rounded-full mt-3 overflow-hidden">
                <div
                  className="bg-neutral-900 h-full transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>

              <div className="mt-4 flex justify-end">
                <button
                  type="button"
                  disabled={analyzingFile || uploadProgress < 100}
                  onClick={handleAnalyzeUploadedFile}
                  className="inline-flex items-center space-x-2 px-4 py-2 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer shadow-xs"
                >
                  {analyzingFile ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Extracting Form Fields...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-3.5 h-3.5" />
                      <span>Extract Fields with AI</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 2: TEMPLATE GALLERY */}
      {activeTab === "template" && !generatedSchema && (
        <div className="mt-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {TEMPLATES.map((tmpl) => (
              <div
                key={tmpl.id}
                className="bg-white border border-[#E5E5E5] hover:border-neutral-900 rounded-xl p-5 flex flex-col justify-between transition-all group shadow-xs cursor-pointer"
                onClick={() => handleSelectTemplate(tmpl)}
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[10px] font-mono uppercase tracking-wider text-neutral-500 bg-[#F7F7F7] px-2 py-0.5 rounded border border-[#E5E5E5]">
                      {tmpl.category}
                    </span>
                    <Sparkles className="w-3.5 h-3.5 text-neutral-400 group-hover:text-black transition-colors" />
                  </div>
                  <h3 className="text-sm font-semibold text-neutral-900 tracking-tight">
                    {tmpl.title}
                  </h3>
                  <p className="text-xs text-[#737373] mt-1 leading-relaxed">
                    {tmpl.description}
                  </p>
                </div>

                <div className="mt-5 pt-3 border-t border-[#E5E5E5] flex items-center justify-between text-xs">
                  <span className="text-[11px] text-neutral-400 font-mono">
                    Instant AI Schema
                  </span>
                  <span className="font-semibold text-neutral-900 group-hover:underline flex items-center space-x-1">
                    <span>Use Template</span>
                    <ArrowRight className="w-3 h-3" />
                  </span>
                </div>
              </div>
            ))}
          </div>

          {generatingTemplate && (
            <div className="mt-6 text-center py-6 bg-[#F7F7F7] rounded-xl border border-[#E5E5E5] flex items-center justify-center space-x-2 text-xs text-neutral-600 font-mono">
              <Loader2 className="w-4 h-4 animate-spin text-neutral-900" />
              <span>Generating schema for {selectedTemplate?.title}...</span>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: BLANK FORM BUILDER */}
      {activeTab === "blank" && !generatedSchema && (
        <form onSubmit={handleSaveBlankForm} className="mt-8 space-y-6">
          <div className="p-5 border border-[#E5E5E5] rounded-xl bg-white space-y-4">
            <div>
              <label className="block text-xs font-semibold text-neutral-900 mb-1">
                Form Title
              </label>
              <input
                type="text"
                required
                value={blankTitle}
                onChange={(e) => setBlankTitle(e.target.value)}
                placeholder="e.g. Employee Verification Form"
                className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 transition-all"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-neutral-900 mb-1">
                Description (Optional)
              </label>
              <input
                type="text"
                value={blankDesc}
                onChange={(e) => setBlankDesc(e.target.value)}
                placeholder="Brief purpose of this form..."
                className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 transition-all"
              />
            </div>
          </div>

          {/* Form Fields List */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-neutral-900 tracking-tight">
                Form Fields ({blankFields.length})
              </h3>
              <button
                type="button"
                onClick={addBlankField}
                className="inline-flex items-center space-x-1 px-2.5 py-1 text-xs border border-[#E5E5E5] hover:border-black rounded-lg transition-colors cursor-pointer"
              >
                <Plus className="w-3 h-3" />
                <span>Add Field</span>
              </button>
            </div>

            {blankFields.map((field, idx) => (
              <div
                key={idx}
                className="p-4 border border-[#E5E5E5] rounded-xl bg-white space-y-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-neutral-500">
                    Field #{idx + 1}
                  </span>
                  <button
                    type="button"
                    onClick={() => removeBlankField(idx)}
                    className="text-neutral-400 hover:text-red-600 transition-colors cursor-pointer"
                    title="Remove field"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                      Label
                    </label>
                    <input
                      type="text"
                      required
                      value={field.label}
                      onChange={(e) => updateBlankField(idx, "label", e.target.value)}
                      placeholder="Field Label"
                      className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-md focus:outline-none focus:border-neutral-900"
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                      Field Type
                    </label>
                    <select
                      value={field.type}
                      onChange={(e) => updateBlankField(idx, "type", e.target.value)}
                      className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-md focus:outline-none focus:border-neutral-900 bg-white"
                    >
                      <option value="text">Text</option>
                      <option value="email">Email</option>
                      <option value="number">Number</option>
                      <option value="date">Date</option>
                      <option value="textarea">Textarea</option>
                      <option value="select">Dropdown / Select</option>
                      <option value="checkbox">Checkbox</option>
                      <option value="radio">Radio Buttons</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                      Placeholder
                    </label>
                    <input
                      type="text"
                      value={field.placeholder || ""}
                      onChange={(e) => updateBlankField(idx, "placeholder", e.target.value)}
                      placeholder="Optional placeholder"
                      className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-md focus:outline-none focus:border-neutral-900"
                    />
                  </div>
                </div>

                <div className="pt-2 flex items-center justify-between border-t border-neutral-100 text-xs">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={field.required}
                      onChange={(e) => updateBlankField(idx, "required", e.target.checked)}
                      className="w-3.5 h-3.5 rounded border-[#E5E5E5] text-neutral-900 focus:ring-neutral-900"
                    />
                    <span className="text-neutral-700">Required field</span>
                  </label>
                  <span className="text-[11px] font-mono text-neutral-400">
                    name: {field.name}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="pt-4 flex justify-end">
            <button
              type="submit"
              disabled={savingBlank}
              className="px-5 py-2.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer shadow-xs"
            >
              {savingBlank ? "Saving to Database..." : "Create Blank Form"}
            </button>
          </div>
        </form>
      )}

      {/* GENERATED SCHEMA PREVIEW, EDITABLE REVIEW & CONFIRMATION */}
      {generatedSchema && (
        <div className="mt-8 border border-[#E5E5E5] rounded-2xl bg-white p-6 sm:p-8 space-y-6 shadow-xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-[#E5E5E5] gap-3">
            <div>
              <div className="flex items-center space-x-2 mb-1">
                <span className="text-[10px] font-mono uppercase tracking-widest text-neutral-400">
                  Document Extraction Result
                </span>
                {extractionMeta?.extraction_strategy && (
                  <span
                    className={`text-[10px] font-mono px-2 py-0.5 rounded-full uppercase font-medium border ${
                      extractionMeta.extraction_strategy === "groq_vision"
                        ? "bg-purple-50 text-purple-700 border-purple-200"
                        : extractionMeta.extraction_strategy === "hybrid"
                        ? "bg-blue-50 text-blue-700 border-blue-200"
                        : extractionMeta.extraction_strategy === "acroform"
                        ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                        : "bg-neutral-100 text-neutral-700 border-neutral-200"
                    }`}
                  >
                    {extractionMeta.extraction_strategy === "groq_vision"
                      ? "Groq Vision OCR"
                      : extractionMeta.extraction_strategy === "hybrid"
                      ? "Hybrid OCR & Text"
                      : extractionMeta.extraction_strategy === "acroform"
                      ? "PDF AcroForm"
                      : "Digital Text"}
                  </span>
                )}
                {extractionMeta?.pages_processed > 1 && (
                  <span className="text-[10px] font-mono text-neutral-400">
                    ({extractionMeta.pages_processed} pages)
                  </span>
                )}
              </div>
              <h2 className="text-lg font-bold text-neutral-900 mt-0.5">
                {generatedSchema.title}
              </h2>
              {generatedSchema.description && (
                <p className="text-xs text-[#737373] mt-1">
                  {generatedSchema.description}
                </p>
              )}
            </div>

            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={() => setPreviewMode(previewMode === "preview" ? "edit" : "preview")}
                className="inline-flex items-center space-x-1.5 px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium transition-colors cursor-pointer"
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span>{previewMode === "preview" ? "Edit Extracted Fields" : "Form Preview"}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setGeneratedSchema(null);
                  setExtractionMeta(null);
                }}
                className="text-xs text-neutral-500 hover:text-black underline cursor-pointer"
              >
                Upload Another
              </button>
            </div>
          </div>

          {/* Uncertain Fields Warning Banner */}
          {extractionMeta?.uncertain_fields_count > 0 && (
            <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-800 flex items-start space-x-2.5">
              <AlertTriangle className="w-4 h-4 shrink-0 text-amber-600 mt-0.5" />
              <div>
                <p className="font-semibold">
                  {extractionMeta.uncertain_fields_count} field(s) were flagged as uncertain or ambiguous.
                </p>
                <p className="text-[11px] text-amber-700 mt-0.5">
                  Review the highlighted fields below to ensure the labels, types, and required validations match your document.
                </p>
              </div>
            </div>
          )}

          {/* PREVIEW MODE: Live Form Renderer */}
          {previewMode === "preview" ? (
            <div>
              <FormRenderer
                schema={generatedSchema}
                values={{}}
                onChange={() => {}}
                disabled={true}
              />
            </div>
          ) : (
            /* EDIT MODE: Editable Fields List */
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-neutral-100">
                <span className="text-xs font-semibold text-neutral-900">
                  Extracted Fields ({generatedSchema.fields?.length || 0})
                </span>
                <button
                  type="button"
                  onClick={() => {
                    const idx = (generatedSchema.fields?.length || 0) + 1;
                    const newField = {
                      name: `field_${idx}`,
                      label: `New Field ${idx}`,
                      type: "text",
                      required: false,
                      placeholder: "",
                      options: [],
                      is_uncertain: false,
                    };
                    setGeneratedSchema({
                      ...generatedSchema,
                      fields: [...(generatedSchema.fields || []), newField],
                    });
                  }}
                  className="inline-flex items-center space-x-1 px-2.5 py-1 text-xs border border-[#E5E5E5] hover:border-black rounded-lg transition-colors cursor-pointer"
                >
                  <Plus className="w-3 h-3" />
                  <span>Add Missing Field</span>
                </button>
              </div>

              <div className="space-y-3 max-h-[460px] overflow-y-auto pr-1">
                {generatedSchema.fields?.map((f, idx) => (
                  <div
                    key={idx}
                    className={`p-4 border rounded-xl space-y-3 ${
                      f.is_uncertain
                        ? "border-amber-300 bg-amber-50/30"
                        : "border-[#E5E5E5] bg-white"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-mono text-neutral-500">
                          #{idx + 1}
                        </span>
                        {f.is_uncertain && (
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 border border-amber-300 font-semibold flex items-center space-x-1">
                            <AlertTriangle className="w-2.5 h-2.5" />
                            <span>Uncertain - Please Review</span>
                          </span>
                        )}
                        {f.source_page && (
                          <span className="text-[10px] font-mono text-neutral-400">
                            Page {f.source_page}
                          </span>
                        )}
                      </div>

                      <button
                        type="button"
                        onClick={() => {
                          const updated = generatedSchema.fields.filter((_, i) => i !== idx);
                          setGeneratedSchema({ ...generatedSchema, fields: updated });
                        }}
                        className="text-neutral-400 hover:text-red-600 transition-colors cursor-pointer"
                        title="Remove field"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div>
                        <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                          Label
                        </label>
                        <input
                          type="text"
                          value={f.label}
                          onChange={(e) => {
                            const updated = [...generatedSchema.fields];
                            updated[idx].label = e.target.value;
                            setGeneratedSchema({ ...generatedSchema, fields: updated });
                          }}
                          className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-md focus:outline-none focus:border-neutral-900 bg-white"
                        />
                      </div>

                      <div>
                        <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                          Type
                        </label>
                        <select
                          value={f.type}
                          onChange={(e) => {
                            const updated = [...generatedSchema.fields];
                            updated[idx].type = e.target.value;
                            setGeneratedSchema({ ...generatedSchema, fields: updated });
                          }}
                          className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-md focus:outline-none focus:border-neutral-900 bg-white"
                        >
                          <option value="text">Text</option>
                          <option value="email">Email</option>
                          <option value="number">Number</option>
                          <option value="date">Date</option>
                          <option value="textarea">Textarea</option>
                          <option value="select">Dropdown / Select</option>
                          <option value="checkbox">Checkbox</option>
                          <option value="radio">Radio</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-[11px] font-medium text-neutral-600 mb-1">
                          Placeholder
                        </label>
                        <input
                          type="text"
                          value={f.placeholder || ""}
                          onChange={(e) => {
                            const updated = [...generatedSchema.fields];
                            updated[idx].placeholder = e.target.value;
                            setGeneratedSchema({ ...generatedSchema, fields: updated });
                          }}
                          className="w-full px-2.5 py-1.5 text-xs border border-[#E5E5E5] rounded-md focus:outline-none focus:border-neutral-900 bg-white"
                        />
                      </div>
                    </div>

                    <div className="pt-2 flex items-center justify-between border-t border-neutral-100 text-xs">
                      <label className="flex items-center space-x-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={Boolean(f.required)}
                          onChange={(e) => {
                            const updated = [...generatedSchema.fields];
                            updated[idx].required = e.target.checked;
                            setGeneratedSchema({ ...generatedSchema, fields: updated });
                          }}
                          className="w-3.5 h-3.5 rounded border-[#E5E5E5] text-neutral-900 focus:ring-neutral-900"
                        />
                        <span className="text-neutral-700">Required field</span>
                      </label>
                      <span className="text-[11px] font-mono text-neutral-400">
                        key: {f.name}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Action to Save to SQLite */}
          <div className="pt-6 border-t border-[#E5E5E5] flex items-center justify-between">
            <span className="text-xs text-neutral-500 font-mono">
              Total validated fields: {generatedSchema.fields?.length || 0}
            </span>
            <button
              disabled={savingSchema}
              onClick={handleSaveToDatabase}
              className="inline-flex items-center space-x-2 px-5 py-2.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-all shadow-xs cursor-pointer disabled:opacity-50"
            >
              <span>{savingSchema ? "Persisting Form..." : "Approve & Start Voice Filling"}</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
