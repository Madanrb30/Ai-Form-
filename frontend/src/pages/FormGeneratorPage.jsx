import React, { useState } from "react";
import { api } from "../services/api";
import FormRenderer from "../components/FormRenderer";

const EXAMPLE_PROMPTS = [
  "Create a student registration form containing full name, register number, department, email address, phone number, date of birth, and gender.",
  "Create a customer feedback survey with name, email, satisfaction rating, service used, would recommend checkbox, and detailed comments.",
  "Create a job application form with candidate name, email, phone number, target position, years of experience, available start date, and cover letter.",
];

export default function FormGeneratorPage({ setView }) {
  const [prompt, setPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [genMeta, setGenMeta] = useState(null);
  const [generatedSchema, setGeneratedSchema] = useState(null);
  const [savedFormId, setSavedFormId] = useState(null);

  const handleGenerate = async (targetPrompt) => {
    const textToUse = targetPrompt || prompt;
    if (!textToUse.trim()) {
      setError("Please enter a description for the form you want to create.");
      return;
    }

    setGenerating(true);
    setError(null);
    setSavedFormId(null);
    try {
      const res = await api.generateForm(textToUse.trim());
      setGeneratedSchema(res.schema_data);
      setGenMeta({
        is_demo: res.is_demo,
        provider: res.provider,
        message: res.message,
      });
    } catch (err) {
      setError(err.message || "Failed to generate form schema");
    } finally {
      setGenerating(false);
    }
  };

  const handleSaveToDatabase = async () => {
    if (!generatedSchema) return;

    setSaving(true);
    setError(null);
    try {
      const created = await api.createForm({
        title: generatedSchema.title,
        description: generatedSchema.description,
        schema_json: generatedSchema,
      });
      setSavedFormId(created.id);
    } catch (err) {
      setError(`Failed to save form to database: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10">
      {/* Title */}
      <div className="pb-6 border-b border-zinc-200">
        <h1 className="text-2xl font-bold tracking-tight text-black m-0">
          AI Form Generator
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          Type instructions in natural language. Our AI engine will structure the schema, field types, and validation rules automatically.
        </p>
      </div>

      {/* Input Section */}
      <div className="mt-8 bg-white border border-zinc-200 p-6 text-left">
        <label className="block text-sm font-semibold text-black mb-2">
          Describe your form requirements:
        </label>
        <textarea
          rows={3}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. Create a student registration form containing full name, register number, department, email address, phone number, date of birth, and gender."
          className="w-full p-3 text-sm border border-zinc-300 focus:outline-none focus:border-black focus:ring-1 focus:ring-black"
        />

        {/* Example prompts */}
        <div className="mt-3">
          <p className="text-xs text-zinc-400 font-mono mb-2">Quick Prompt Examples:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_PROMPTS.map((ex, i) => (
              <button
                key={i}
                type="button"
                onClick={() => {
                  setPrompt(ex);
                  handleGenerate(ex);
                }}
                className="text-xs px-2.5 py-1 bg-zinc-100 hover:bg-zinc-200 text-zinc-800 transition-colors cursor-pointer border border-zinc-200 text-left"
              >
                {i === 0 ? "Student Registration" : i === 1 ? "Customer Feedback" : "Job Application"}
              </button>
            ))}
          </div>
        </div>

        {/* Generate Action */}
        <div className="mt-6 flex items-center justify-between">
          <button
            disabled={generating || !prompt.trim()}
            onClick={() => handleGenerate(prompt)}
            className="px-5 py-2.5 bg-black text-white text-sm font-medium hover:bg-zinc-800 disabled:bg-zinc-300 disabled:cursor-not-allowed transition-colors"
          >
            {generating ? "Generating Schema..." : "Generate Form"}
          </button>
          {generating && (
            <span className="text-xs text-zinc-500 font-mono animate-pulse">
              Synthesizing fields and validation rules...
            </span>
          )}
        </div>
      </div>

      {/* Error message */}
      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 text-sm text-red-700 text-left">
          <p className="font-semibold">Error:</p>
          <p>{error}</p>
        </div>
      )}

      {/* Success Notification after Save */}
      {savedFormId && (
        <div className="mt-6 p-4 bg-emerald-50 border border-emerald-300 text-sm text-emerald-800 flex items-center justify-between text-left">
          <div>
            <p className="font-semibold">Form saved successfully to database! (ID: {savedFormId})</p>
            <p className="text-xs text-emerald-700 mt-0.5">
              You can now fill this form manually or with voice input.
            </p>
          </div>
          <div className="flex space-x-2">
            <button
              onClick={() => setView({ name: "fill", formId: savedFormId })}
              className="px-3 py-1.5 bg-black text-white text-xs font-medium hover:bg-zinc-800"
            >
              Fill Now
            </button>
            <button
              onClick={() => setView({ name: "dashboard" })}
              className="px-3 py-1.5 border border-zinc-300 text-xs font-medium bg-white text-zinc-800 hover:bg-zinc-100"
            >
              Back to Forms
            </button>
          </div>
        </div>
      )}

      {/* Generated Schema Preview */}
      {generatedSchema && (
        <div className="mt-8 border border-zinc-200 bg-white p-6 sm:p-8 text-left">
          {/* Header & Meta Badge */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-6 border-b border-zinc-200 gap-2">
            <div>
              <span className="text-xs uppercase tracking-widest font-mono text-zinc-400">
                Form Preview
              </span>
              <h2 className="text-xl font-bold text-black mt-1">
                {generatedSchema.title}
              </h2>
              {generatedSchema.description && (
                <p className="text-xs text-zinc-500 mt-1">
                  {generatedSchema.description}
                </p>
              )}
            </div>

            <div className="flex flex-col items-start sm:items-end">
              <span
                className={`text-xs px-2.5 py-1 font-mono border ${
                  genMeta?.is_demo
                    ? "bg-zinc-100 border-zinc-300 text-zinc-700"
                    : "bg-emerald-50 border-emerald-300 text-emerald-800"
                }`}
              >
                {genMeta?.is_demo ? "Demo Mode Generator" : `Provider: ${genMeta?.provider}`}
              </span>
              {genMeta?.message && (
                <span className="text-[11px] text-zinc-400 mt-1 max-w-xs text-left sm:text-right">
                  {genMeta.message}
                </span>
              )}
            </div>
          </div>

          {/* Render Preview fields */}
          <div className="mt-6">
            <FormRenderer
              schema={generatedSchema}
              values={{}}
              onChange={() => {}}
              disabled={true}
            />
          </div>

          {/* Action to Save */}
          <div className="mt-8 pt-6 border-t border-zinc-200 flex items-center justify-between">
            <span className="text-xs text-zinc-400 font-mono">
              Total fields: {generatedSchema.fields?.length || 0}
            </span>
            <button
              disabled={saving || Boolean(savedFormId)}
              onClick={handleSaveToDatabase}
              className="px-5 py-2.5 bg-black text-white text-sm font-medium hover:bg-zinc-800 disabled:bg-zinc-300 disabled:cursor-not-allowed transition-colors"
            >
              {saving ? "Saving to Database..." : savedFormId ? "Form Saved" : "Save Form to Database"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
