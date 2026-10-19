import React, { useEffect, useState, useCallback } from "react";
import {
  ArrowLeft,
  FileCheck,
  Download,
  FileSpreadsheet,
  Mic,
  Loader2,
  Eye,
  X,
  Search,
  Filter,
  RotateCcw,
} from "lucide-react";
import { api } from "../services/api";
import { useToast } from "../context/ToastContext";

export default function SubmissionsPage({ formId, formTitle, setView }) {
  const { toast } = useToast();

  const [form, setForm] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);
  const [detailModalSub, setDetailModalSub] = useState(null);
  const [exportingExcel, setExportingExcel] = useState(false);

  // Filter States
  const [searchQuery, setSearchQuery] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [appliedFilters, setAppliedFilters] = useState({ search: "", startDate: "", endDate: "" });

  const loadData = useCallback(async (filtersToUse) => {
    setLoading(true);
    setError(null);
    try {
      const [formData, subsData] = await Promise.all([
        api.getForm(formId),
        api.getSubmissions(formId, filtersToUse),
      ]);
      setForm(formData);
      setSubmissions(subsData || []);
    } catch (err) {
      setError(err.message || "Failed to load submission history.");
    } finally {
      setLoading(false);
    }
  }, [formId]);

  useEffect(() => {
    loadData(appliedFilters);
  }, [loadData, appliedFilters]);

  const handleApplyFilters = (e) => {
    if (e) e.preventDefault();
    setAppliedFilters({
      search: searchQuery.trim(),
      startDate,
      endDate,
    });
  };

  const handleClearFilters = () => {
    setSearchQuery("");
    setStartDate("");
    setEndDate("");
    setAppliedFilters({ search: "", startDate: "", endDate: "" });
  };

  const hasActiveFilters = Boolean(
    appliedFilters.search || appliedFilters.startDate || appliedFilters.endDate
  );

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
    const filterSuffix = hasActiveFilters ? "_filtered" : "";
    link.download = `${form.title.replace(/[^a-z0-9]/gi, "_")}_submissions${filterSuffix}.csv`;
    link.click();
    URL.revokeObjectURL(url);
    toast("Exported submissions as CSV.", "success");
  };

  const handleExportExcel = async () => {
    if (!form || exportingExcel) return;
    setExportingExcel(true);
    try {
      toast("Generating Excel spreadsheet...", "info");
      const cleanTitle = (form?.title || "Form").replace(/[^a-zA-Z0-9_-]/g, "_");
      await api.exportSubmissionsExcel(
        formId,
        appliedFilters,
        `${cleanTitle}_Submissions.xlsx`
      );
      toast("Excel workbook exported successfully.", "success");
    } catch (err) {
      toast(`Excel export failed: ${err.message}`, "error");
    } finally {
      setExportingExcel(false);
    }
  };

  const handleDownloadPdf = async (subId) => {
    if (downloadingId) return;
    setDownloadingId(subId);
    try {
      toast("Generating and downloading PDF...", "info");
      await api.downloadSubmissionPdf(formId, subId, `${form?.title || 'Form'}_Submission_${subId}.pdf`);
      toast("PDF downloaded successfully.", "success");
    } catch (err) {
      toast(`PDF download failed: ${err.message}`, "error");
    } finally {
      setDownloadingId(null);
    }
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
          <div className="min-w-0">
            <h1 className="text-xl font-bold tracking-tight text-neutral-900 break-words">
              {form?.title || "Form"} Submissions
            </h1>
            <p className="text-xs text-[#737373] mt-0.5">
              Recorded responses stored in SQLite. Showing {submissions.length} {hasActiveFilters ? "filtered" : "total"}.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {submissions.length > 0 && (
            <>
              <button
                type="button"
                onClick={handleExportCsv}
                className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer"
                title="Export current submissions as CSV"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Export CSV</span>
              </button>

              <button
                type="button"
                onClick={handleExportExcel}
                disabled={exportingExcel}
                className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black transition-colors flex items-center space-x-1.5 cursor-pointer disabled:opacity-50"
                title="Export formatted Excel workbook (.xlsx)"
              >
                {exportingExcel ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Exporting Excel...</span>
                  </>
                ) : (
                  <>
                    <FileSpreadsheet className="w-3.5 h-3.5 text-neutral-700" />
                    <span>Export Excel</span>
                  </>
                )}
              </button>
            </>
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

      {/* Filter Toolbar */}
      <form
        onSubmit={handleApplyFilters}
        className="mt-6 p-4 bg-white border border-[#E5E5E5] rounded-xl shadow-xs flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3 text-xs"
      >
        <div className="flex-1 flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          {/* Keyword Search */}
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by respondent, ID, or value..."
              className="w-full pl-9 pr-3 py-1.5 border border-[#E5E5E5] rounded-lg text-xs focus:outline-none focus:border-black transition-colors"
            />
          </div>

          {/* Date Range */}
          <div className="flex items-center space-x-2">
            <div className="flex items-center space-x-1.5">
              <span className="text-[11px] text-neutral-500 font-medium">From:</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="px-2 py-1.5 border border-[#E5E5E5] rounded-lg text-xs focus:outline-none focus:border-black font-mono"
              />
            </div>
            <div className="flex items-center space-x-1.5">
              <span className="text-[11px] text-neutral-500 font-medium">To:</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="px-2 py-1.5 border border-[#E5E5E5] rounded-lg text-xs focus:outline-none focus:border-black font-mono"
              />
            </div>
          </div>
        </div>

        {/* Filter Action Buttons */}
        <div className="flex items-center space-x-2 shrink-0">
          <button
            type="submit"
            className="px-3 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg font-medium transition-colors cursor-pointer flex items-center space-x-1"
          >
            <Filter className="w-3 h-3" />
            <span>Apply</span>
          </button>

          {hasActiveFilters && (
            <button
              type="button"
              onClick={handleClearFilters}
              className="px-2.5 py-1.5 border border-[#E5E5E5] hover:bg-neutral-100 text-neutral-600 rounded-lg font-medium transition-colors cursor-pointer flex items-center space-x-1"
              title="Reset Filters"
            >
              <RotateCcw className="w-3 h-3" />
              <span>Clear</span>
            </button>
          )}
        </div>
      </form>

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

            const isThisDownloading = downloadingId === sub.id;

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
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-neutral-500 text-[11px] mr-2">
                      {subDate}
                    </span>
                    <button
                      type="button"
                      onClick={() => setDetailModalSub(sub)}
                      className="inline-flex items-center space-x-1 px-2.5 py-1 bg-white hover:bg-neutral-50 border border-[#E5E5E5] hover:border-black rounded-lg text-[11px] font-medium text-neutral-700 transition-colors cursor-pointer"
                    >
                      <Eye className="w-3 h-3 text-neutral-500" />
                      <span>Details</span>
                    </button>
                    <button
                      type="button"
                      disabled={isThisDownloading}
                      onClick={() => handleDownloadPdf(sub.id)}
                      className="inline-flex items-center space-x-1 px-2.5 py-1 bg-neutral-50 hover:bg-neutral-100 border border-[#E5E5E5] hover:border-black rounded-lg text-[11px] font-semibold text-neutral-800 transition-colors cursor-pointer disabled:opacity-50"
                      title="Download Generated Completed PDF Document"
                    >
                      {isThisDownloading ? (
                        <Loader2 className="w-3 h-3 animate-spin text-neutral-600" />
                      ) : (
                        <Download className="w-3 h-3 text-neutral-600" />
                      )}
                      <span>{isThisDownloading ? "Downloading..." : "PDF"}</span>
                    </button>
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

      {/* View Details Modal */}
      {detailModalSub && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs">
          <div className="bg-white border border-[#E5E5E5] rounded-2xl max-w-2xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#E5E5E5]">
              <div>
                <h3 className="text-sm font-bold text-neutral-900">
                  Submission Details #{detailModalSub.id}
                </h3>
                <p className="text-[11px] text-[#737373] mt-0.5 font-mono">
                  Submitted: {new Date(detailModalSub.created_at).toLocaleString()}
                </p>
              </div>
              <button
                onClick={() => setDetailModalSub(null)}
                className="p-1 rounded-lg text-neutral-400 hover:text-black hover:bg-neutral-100 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {Object.entries(detailModalSub.response_json || {}).map(([key, val]) => {
                  const fieldDef = form?.schema_json?.fields?.find((f) => f.name === key);
                  const label = fieldDef?.label || key;
                  return (
                    <div
                      key={key}
                      className="p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl"
                    >
                      <span className="block text-[11px] font-medium text-neutral-500">
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

            {/* Modal Footer */}
            <div className="px-6 py-3.5 border-t border-[#E5E5E5] bg-[#F7F7F7] flex items-center justify-between">
              <button
                type="button"
                onClick={() => setDetailModalSub(null)}
                className="px-3 py-1.5 border border-[#E5E5E5] hover:border-black rounded-lg text-xs font-medium text-neutral-700 hover:text-black bg-white transition-colors cursor-pointer"
              >
                Close
              </button>

              <button
                type="button"
                disabled={downloadingId === detailModalSub.id}
                onClick={() => handleDownloadPdf(detailModalSub.id)}
                className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer disabled:opacity-50"
              >
                {downloadingId === detailModalSub.id ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Download className="w-3.5 h-3.5" />
                )}
                <span>
                  {downloadingId === detailModalSub.id
                    ? "Downloading..."
                    : "Download PDF"}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
