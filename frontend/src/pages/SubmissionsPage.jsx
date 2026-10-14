import React, { useEffect, useState } from "react";
import {
  ArrowLeft,
  FileCheck,
  Download,
  Mic,
  Calendar,
  Hash,
  Share2,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";

export default function SubmissionsPage({ formId, formTitle, setView }) {
  const { toast } = useToast();

  const [form, setForm] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let isMounted = true;
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [formData, subsData] = await Promise.all([
          api.getForm(formId),
          api.getSubmissions(formId),
        ]);
        if (isMounted) {
          setForm(formData);
          setSubmissions(subsData);
        }
      } catch (err) {
        if (isMounted) {
          setError(err.message || "Failed to load submission history.");
        }
      } finally {
        if (isMounted) setLoading(false);
      }
    };

    loadData();
    return () => {
      isMounted = false;
    };
  }, [formId]);

  const handleExportCsv = () => {
    if (!form || submissions.length === 0) return;

    const fields = form.schema_json?.fields || [];
    const headers = ["Submission ID", "Timestamp", ...fields.map((f) => f.label)];

    const rows = submissions.map((sub) => {
      const row = [
        sub.id,
        new Date(sub.created_at).toISOString(),
        ...fields.map((f) => {
          const val = sub.response_json?.[f.name];
          if (val === undefined || val === null) return "";
          return `"${String(val).replace(/"/g, '""')}"`;
        }),
      ];
      return row.join(",");
    });

    const csvContent = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${form.title.replace(/[^a-z0-9]/gi, "_")}_submissions.csv`;
    link.click();
    URL.revokeObjectURL(url);
    toast("Exported submissions as CSV.", "success");
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-8 py-8 text-left">
      {/* Header */}
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
              {form?.title || "Form"} Submissions
            </h1>
            <p className="text-xs text-[#737373] mt-0.5">
              Recorded responses stored in SQLite. Total: {submissions.length}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {submissions.length > 0 && (
            <button
              onClick={handleExportCsv}
              className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export CSV</span>
            </button>
          )}

          <button
            onClick={() =>
              setView({
                name: "fill",
                formId,
                formTitle: form?.title,
              })
            }
            className="px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors flex items-center space-x-1.5 cursor-pointer shadow-xs"
          >
            <Mic className="w-3.5 h-3.5" />
            <span>Voice Fill New Response</span>
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="py-20 text-center">
          <div className="inline-block w-6 h-6 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-[#737373] mt-2 font-mono">Loading responses...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && submissions.length === 0 && (
        <div className="mt-10 text-center py-16 border border-dashed border-[#E5E5E5] rounded-2xl bg-[#F7F7F7] px-6">
          <div className="w-12 h-12 bg-white border border-[#E5E5E5] rounded-xl flex items-center justify-center mx-auto mb-4 shadow-xs">
            <FileCheck className="w-6 h-6 text-neutral-400" />
          </div>
          <h3 className="text-sm font-semibold text-neutral-900">No submissions yet</h3>
          <p className="text-xs text-[#737373] max-w-sm mx-auto mt-1 mb-6">
            This form hasn&apos;t received any responses yet. Fill it out using voice assistant or manual entry.
          </p>
          <button
            onClick={() =>
              setView({
                name: "fill",
                formId,
                formTitle: form?.title,
              })
            }
            className="px-4 py-2 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          >
            Submit First Response
          </button>
        </div>
      )}

      {/* Submissions List */}
      {!loading && !error && submissions.length > 0 && (
        <div className="mt-8 space-y-4">
          {submissions.map((sub, index) => {
            const subDate = new Date(sub.created_at).toLocaleString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            });

            return (
              <div
                key={sub.id}
                className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs hover:border-neutral-400 transition-colors"
              >
                <div className="flex items-center justify-between pb-3 border-b border-[#E5E5E5] text-xs">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono font-bold text-neutral-900">
                      Response #{submissions.length - index}
                    </span>
                    <span className="text-[11px] font-mono text-neutral-400">
                      (ID: {sub.id})
                    </span>
                  </div>
                  <div className="flex items-center space-x-3">
                    <span className="font-mono text-neutral-500 text-[11px]">
                      {subDate}
                    </span>
                    <a
                      href={api.getSubmissionPdfUrl(formId, sub.id)}
                      download={`submission_${sub.id}.pdf`}
                      className="inline-flex items-center space-x-1 px-2.5 py-1 bg-neutral-50 hover:bg-neutral-100 border border-[#E5E5E5] hover:border-black rounded-lg text-[11px] font-semibold text-neutral-800 transition-colors cursor-pointer"
                      title="Download Generated Completed PDF Document"
                    >
                      <Download className="w-3 h-3 text-neutral-600" />
                      <span>PDF</span>
                    </a>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 mt-4 text-xs">
                  {Object.entries(sub.response_json || {}).map(([key, val]) => {
                    const fieldDef = form?.schema_json?.fields?.find((f) => f.name === key);
                    const label = fieldDef?.label || key;

                    return (
                      <div
                        key={key}
                        className="bg-[#F7F7F7] border border-[#E5E5E5] p-3 rounded-xl"
                      >
                        <span className="block text-[11px] font-medium text-neutral-500 truncate">
                          {label}
                        </span>
                        <span className="block font-semibold text-neutral-900 mt-1 break-words">
                          {typeof val === "boolean"
                            ? val
                              ? "Yes / Checked"
                              : "No / Unchecked"
                            : String(val || "—")}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
