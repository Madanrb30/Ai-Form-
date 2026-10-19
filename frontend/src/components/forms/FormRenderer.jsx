import React from "react";
import { Sparkles, FileText, AlertTriangle, Edit3 } from "lucide-react";

export default function FormRenderer({
  schema,
  values = {},
  onChange,
  errors = {},
  disabled = false,
  highlightedFields = [],
  aiFilledFields = [],
  pdfFilledFields = [],
  needsReviewFields = {},
  manuallyEditedFields = [],
  missingFields = [],
  onFieldManualEdit,
}) {
  if (!schema || !schema.fields || schema.fields.length === 0) {
    return (
      <div className="text-neutral-500 py-10 text-center text-xs border border-dashed border-[#E5E5E5] rounded-xl bg-[#F7F7F7]">
        No fields defined for this form.
      </div>
    );
  }

  const handleInputChange = (name, value) => {
    if (disabled || !onChange) return;
    if (onFieldManualEdit) {
      onFieldManualEdit(name);
    }
    onChange({
      ...values,
      [name]: value,
    });
  };

  const handleCheckboxChange = (name, checked) => {
    if (disabled || !onChange) return;
    if (onFieldManualEdit) {
      onFieldManualEdit(name);
    }
    onChange({
      ...values,
      [name]: checked,
    });
  };

  return (
    <div className="space-y-5">
      {schema.fields.map((field) => {
        const value =
          values[field.name] !== undefined
            ? values[field.name]
            : (field.default_value ?? "");
        const error = errors[field.name];
        const isHighlighted = highlightedFields.includes(field.name);
        const isPdfFilled = pdfFilledFields.includes(field.name);
        const isAiFilled = aiFilledFields.includes(field.name) && !isPdfFilled;
        const isManuallyEdited = manuallyEditedFields.includes(field.name);
        const reviewNote = needsReviewFields[field.name];
        const isMissing = missingFields.includes(field.name) || (field.required && (value === undefined || value === null || String(value).trim() === "" || value === false));

        return (
          <div
            key={field.name}
            className={`p-3.5 rounded-xl border transition-all duration-300 text-left ${
              isHighlighted
                ? "border-neutral-900 bg-neutral-50 ai-field-highlight ring-1 ring-neutral-900/10"
                : reviewNote
                ? "border-amber-300 bg-amber-50/30"
                : "border-[#E5E5E5] bg-white hover:border-neutral-300"
            }`}
          >
            {/* Field Header */}
            <div className="flex flex-wrap justify-between items-center gap-1.5 mb-1.5">
              <label
                htmlFor={`field-${field.name}`}
                className="text-xs font-semibold text-neutral-900 flex items-center space-x-1.5 break-words"
              >
                <span>{field.label}</span>
                {field.required && (
                  <span className="text-red-500 font-bold" title="Required field">
                    *
                  </span>
                )}
                {isMissing && isPdfFilled === false && field.required && (
                  <span className="text-[10px] text-neutral-400 font-normal font-mono italic">
                    (Incomplete)
                  </span>
                )}
              </label>

              <div className="flex flex-wrap items-center gap-1.5">
                {isPdfFilled && (
                  <span className="inline-flex items-center space-x-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-900 text-white">
                    <FileText className="w-2.5 h-2.5 text-neutral-300" />
                    <span>From PDF</span>
                  </span>
                )}
                {isAiFilled && (
                  <span className="inline-flex items-center space-x-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-900 text-white">
                    <Sparkles className="w-2.5 h-2.5 text-neutral-200" />
                    <span>AI Filled</span>
                  </span>
                )}
                {isManuallyEdited && (
                  <span className="inline-flex items-center space-x-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-100 text-neutral-700 border border-neutral-300">
                    <Edit3 className="w-2.5 h-2.5 text-neutral-500" />
                    <span>Edited</span>
                  </span>
                )}
                {reviewNote && (
                  <span className="inline-flex items-center space-x-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-300">
                    <AlertTriangle className="w-2.5 h-2.5 text-amber-600" />
                    <span>Review Needed</span>
                  </span>
                )}
                <span className="text-[10px] font-mono text-neutral-400 bg-neutral-100 px-1.5 py-0.5 rounded">
                  {field.type}
                </span>
              </div>
            </div>

            {/* Input Controls */}
            {field.type === "text" && (
              <input
                id={`field-${field.name}`}
                type="text"
                disabled={disabled}
                placeholder={field.placeholder || `Enter ${field.label.toLowerCase()}`}
                value={value}
                onChange={(e) => handleInputChange(field.name, e.target.value)}
                className={`w-full px-3 py-2 text-xs rounded-lg border bg-white focus:outline-none transition-all ${
                  error
                    ? "border-red-500 focus:ring-1 focus:ring-red-500"
                    : reviewNote
                    ? "border-amber-300 focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                    : "border-[#E5E5E5] focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                } disabled:bg-neutral-100 disabled:text-neutral-400`}
              />
            )}

            {field.type === "email" && (
              <input
                id={`field-${field.name}`}
                type="email"
                disabled={disabled}
                placeholder={field.placeholder || "name@example.com"}
                value={value}
                onChange={(e) => handleInputChange(field.name, e.target.value)}
                className={`w-full px-3 py-2 text-xs rounded-lg border bg-white focus:outline-none transition-all ${
                  error
                    ? "border-red-500 focus:ring-1 focus:ring-red-500"
                    : reviewNote
                    ? "border-amber-300 focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                    : "border-[#E5E5E5] focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                } disabled:bg-neutral-100 disabled:text-neutral-400`}
              />
            )}

            {field.type === "number" && (
              <input
                id={`field-${field.name}`}
                type="number"
                disabled={disabled}
                placeholder={field.placeholder || "0"}
                value={value}
                onChange={(e) => handleInputChange(field.name, e.target.value)}
                className={`w-full px-3 py-2 text-xs rounded-lg border bg-white focus:outline-none transition-all ${
                  error
                    ? "border-red-500 focus:ring-1 focus:ring-red-500"
                    : reviewNote
                    ? "border-amber-300 focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                    : "border-[#E5E5E5] focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                } disabled:bg-neutral-100 disabled:text-neutral-400`}
              />
            )}

            {field.type === "date" && (
              <input
                id={`field-${field.name}`}
                type="date"
                disabled={disabled}
                value={value}
                onChange={(e) => handleInputChange(field.name, e.target.value)}
                className={`w-full px-3 py-2 text-xs rounded-lg border bg-white focus:outline-none transition-all ${
                  error
                    ? "border-red-500 focus:ring-1 focus:ring-red-500"
                    : reviewNote
                    ? "border-amber-300 focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                    : "border-[#E5E5E5] focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                } disabled:bg-neutral-100 disabled:text-neutral-400`}
              />
            )}

            {field.type === "textarea" && (
              <textarea
                id={`field-${field.name}`}
                rows={3}
                disabled={disabled}
                placeholder={field.placeholder || "Enter details..."}
                value={value}
                onChange={(e) => handleInputChange(field.name, e.target.value)}
                className={`w-full px-3 py-2 text-xs rounded-lg border bg-white focus:outline-none transition-all ${
                  error
                    ? "border-red-500 focus:ring-1 focus:ring-red-500"
                    : reviewNote
                    ? "border-amber-300 focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                    : "border-[#E5E5E5] focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                } disabled:bg-neutral-100 disabled:text-neutral-400`}
              />
            )}

            {field.type === "select" && (
              <select
                id={`field-${field.name}`}
                disabled={disabled}
                value={value}
                onChange={(e) => handleInputChange(field.name, e.target.value)}
                className={`w-full px-3 py-2 text-xs rounded-lg border bg-white focus:outline-none transition-all ${
                  error
                    ? "border-red-500 focus:ring-1 focus:ring-red-500"
                    : reviewNote
                    ? "border-amber-300 focus:border-amber-500 focus:ring-1 focus:ring-amber-500"
                    : "border-[#E5E5E5] focus:border-neutral-900 focus:ring-1 focus:ring-neutral-900"
                } disabled:bg-neutral-100 disabled:text-neutral-400`}
              >
                <option value="">-- Select an option --</option>
                {(field.options || []).map((opt, i) => (
                  <option key={i} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            )}

            {field.type === "checkbox" && (
              <div className="flex items-center space-x-2.5 pt-1">
                <input
                  id={`field-${field.name}`}
                  type="checkbox"
                  disabled={disabled}
                  checked={Boolean(value)}
                  onChange={(e) => handleCheckboxChange(field.name, e.target.checked)}
                  className="w-4 h-4 text-neutral-900 border-[#E5E5E5] rounded focus:ring-neutral-900 cursor-pointer"
                />
                <span className="text-xs text-neutral-700">
                  {field.placeholder || "Confirm / Accept"}
                </span>
              </div>
            )}

            {field.type === "radio" && (
              <div className="space-y-1.5 pt-1">
                {(field.options || []).map((opt, idx) => (
                  <label
                    key={idx}
                    className="flex items-center space-x-2 cursor-pointer text-xs text-neutral-800"
                  >
                    <input
                      type="radio"
                      name={field.name}
                      disabled={disabled}
                      value={opt}
                      checked={value === opt}
                      onChange={() => handleInputChange(field.name, opt)}
                      className="w-3.5 h-3.5 text-neutral-900 border-[#E5E5E5] focus:ring-neutral-900"
                    />
                    <span>{opt}</span>
                  </label>
                ))}
              </div>
            )}

            {/* Review Note Notice */}
            {reviewNote && (
              <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-1.5 mt-2 font-mono flex items-start space-x-1.5">
                <AlertTriangle className="w-3 h-3 text-amber-600 shrink-0 mt-0.5" />
                <span>
                  <strong className="font-semibold">Review note:</strong> {reviewNote}
                </span>
              </p>
            )}

            {/* Error Message */}
            {error && (
              <p className="text-[11px] text-red-600 mt-1 font-medium">{error}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}
