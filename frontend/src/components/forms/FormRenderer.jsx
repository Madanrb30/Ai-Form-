import React from "react";
import { Sparkles } from "lucide-react";

export default function FormRenderer({
  schema,
  values = {},
  onChange,
  errors = {},
  disabled = false,
  highlightedFields = [],
  aiFilledFields = [],
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
    onChange({
      ...values,
      [name]: value,
    });
  };

  const handleCheckboxChange = (name, checked) => {
    if (disabled || !onChange) return;
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
        const isAiFilled = aiFilledFields.includes(field.name);

        return (
          <div
            key={field.name}
            className={`p-3.5 rounded-xl border transition-all duration-300 text-left ${
              isHighlighted
                ? "border-neutral-900 bg-neutral-50 ai-field-highlight ring-1 ring-neutral-900/10"
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
              </label>

              <div className="flex items-center space-x-1.5">
                {isAiFilled && (
                  <span className="inline-flex items-center space-x-1 text-[10px] font-mono px-1.5 py-0.5 rounded bg-neutral-900 text-white">
                    <Sparkles className="w-2.5 h-2.5 text-neutral-200" />
                    <span>AI Filled</span>
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
