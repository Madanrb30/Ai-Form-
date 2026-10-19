import React, { useEffect, useState } from "react";
import {
  History,
  Search,
  CheckCircle2,
  Clock,
  Download,
  Trash2,
  FileText,
  Eye,
  Edit3,
  Loader2,
  ArrowRight,
  Mic,
  Calendar,
} from "lucide-react";
import { api } from "../services/api";
import { storageService } from "../services/storageService";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import Modal from "../components/common/Modal";

export default function HistoryPage({ setView }) {
  const { user } = useAuth();
  const { toast } = useToast();

  // Data states
  const [submissions, setSubmissions] = useState([]);
  const [forms, setForms] = useState([]);
  const [submissionsMap, setSubmissionsMap] = useState({});
  const [draftsMap, setDraftsMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Tab & Filters: 'submissions' | 'forms' | 'drafts'
  const [activeTab, setActiveTab] = useState("submissions");
  const [search, setSearch] = useState("");
  const [sortOrder, setSortOrder] = useState("newest"); // 'newest' | 'oldest'

  // Submission Details Modal
  const [selectedSubmission, setSelectedSubmission] = useState(null);

  // PDF Downloading State
  const [downloadingId, setDownloadingId] = useState(null);

  // Delete Form Modal
  const [deleteFormTarget, setDeleteFormTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmDeleteSubmissionsChecked, setConfirmDeleteSubmissionsChecked] = useState(false);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [userSubs, formsList] = await Promise.all([
        api.getUserSubmissions().catch(() => []),
        api.getForms().catch(() => []),
      ]);

      setSubmissions(userSubs || []);
      setForms(formsList || []);

      const localDrafts = storageService.getDrafts(user?.id);
      setDraftsMap(localDrafts || {});

      // Build submission count mapping for forms list
      const subMap = {};
      for (const s of userSubs || []) {
        if (!subMap[s.form_id]) subMap[s.form_id] = [];
        subMap[s.form_id].push(s);
      }
      setSubmissionsMap(subMap);
    } catch (err) {
      setError(err.message || "Failed to load submission history.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [user?.id]);

  const handleDownloadPdf = async (sub) => {
    if (!sub || downloadingId === sub.id) return;
    setDownloadingId(sub.id);
    try {
      toast("Generating and preparing completed PDF...", "info");
      const safeTitle = (sub.form_title || "Form").replace(/[^a-zA-Z0-9_-]/g, "_");
      await api.downloadSubmissionPdf(
        sub.form_id,
        sub.id,
        `${safeTitle}_Submission_${sub.id}.pdf`
      );
      toast("PDF downloaded successfully.", "success");
    } catch (err) {
      toast(`PDF download failed: ${err.message}`, "error");
    } finally {
      setDownloadingId(null);
    }
  };

  const confirmDeleteForm = async () => {
    if (!deleteFormTarget || deleting) return;
    setDeleting(true);
    try {
      await api.deleteForm(deleteFormTarget.id, {
        confirmDeleteSubmissions: confirmDeleteSubmissionsChecked,
      });
      storageService.deleteDraft(deleteFormTarget.id, user?.id);
      setForms((prev) => prev.filter((f) => f.id !== deleteFormTarget.id));
      toast(`Form "${deleteFormTarget.title}" deleted successfully.`, "info");
      setDeleteFormTarget(null);
      setConfirmDeleteSubmissionsChecked(false);
      loadData();
    } catch (err) {
      toast(`Failed to delete form: ${err.message}`, "error");
    } finally {
      setDeleting(false);
    }
  };

  const handleExportFormJson = (formItem) => {
    const subs = submissionsMap[formItem.id] || [];
    const draft = draftsMap[formItem.id] || null;
    const exportData = {
      form: formItem,
      draft,
      submissions: subs,
      exportedAt: new Date().toISOString(),
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${formItem.title.replace(/[^a-z0-9]/gi, "_").toLowerCase()}_export.json`;
    a.click();
    URL.revokeObjectURL(url);
    toast("Form data exported as JSON.", "success");
  };

  // Filter & Sort Submissions
  const filteredSubmissions = submissions
    .filter((sub) => {
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      const titleMatch = (sub.form_title || "").toLowerCase().includes(q);
      const idMatch = String(sub.id).includes(q);
      const valuesMatch = Object.values(sub.response_json || {}).some((v) =>
        String(v).toLowerCase().includes(q)
      );
      return titleMatch || idMatch || valuesMatch;
    })
    .sort((a, b) => {
      const dateA = new Date(a.created_at).getTime();
      const dateB = new Date(b.created_at).getTime();
      return sortOrder === "newest" ? dateB - dateA : dateA - dateB;
    });

  // Filter & Sort Forms
  const filteredForms = forms
    .filter((f) => {
      if (!search.trim()) return true;
      const q = search.toLowerCase();
      return (
        f.title.toLowerCase().includes(q) ||
        (f.description && f.description.toLowerCase().includes(q))
      );
    })
    .sort((a, b) => {
      const dateA = new Date(a.created_at).getTime();
      const dateB = new Date(b.created_at).getTime();
      return sortOrder === "newest" ? dateB - dateA : dateA - dateB;
    });

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-8 py-8 text-left">
      {/* Header */}
      <div className="pb-6 border-b border-[#E5E5E5]">
        <div className="flex items-center space-x-2">
          <History className="w-5 h-5 text-neutral-900" />
          <h1 className="text-xl font-bold tracking-tight text-neutral-900">
            Submission History
          </h1>
        </div>
        <p className="text-xs text-[#737373] mt-1">
          Review, inspect details, and download completed PDF documents for your submitted responses.
        </p>
      </div>

      {/* Navigation Tabs and Search Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mt-6 border-b border-[#E5E5E5] pb-4">
        {/* Tabs */}
        <div className="flex space-x-2">
          <button
            onClick={() => setActiveTab("submissions")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "submissions"
                ? "bg-[#111111] text-white shadow-xs"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            My Submissions ({submissions.length})
          </button>
          <button
            onClick={() => setActiveTab("forms")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "forms"
                ? "bg-[#111111] text-white shadow-xs"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            My Forms ({forms.length})
          </button>
          <button
            onClick={() => setActiveTab("drafts")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "drafts"
                ? "bg-[#111111] text-white shadow-xs"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            Drafts ({Object.keys(draftsMap).length})
          </button>
        </div>

        {/* Search & Sort */}
        <div className="flex items-center space-x-2.5">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              placeholder="Search history..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-1.5 text-xs bg-[#F7F7F7] border border-[#E5E5E5] rounded-lg focus:bg-white focus:outline-none focus:border-neutral-900 w-48 transition-all"
            />
          </div>

          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
            className="px-2.5 py-1.5 text-xs bg-[#F7F7F7] border border-[#E5E5E5] rounded-lg focus:outline-none text-neutral-700 cursor-pointer"
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
          </select>
        </div>
      </div>

      {/* Loading Skeleton */}
      {loading && (
        <div className="py-20 text-center">
          <div className="inline-block w-6 h-6 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-[#737373] mt-2 font-mono">Loading history records...</p>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex justify-between items-center">
          <span>{error}</span>
          <button onClick={loadData} className="underline font-semibold ml-4 cursor-pointer">
            Retry
          </button>
        </div>
      )}

      {/* TAB 1: MY SUBMISSIONS (PRIMARY SUBMISSION HISTORY) */}
      {!loading && !error && activeTab === "submissions" && (
        <>
          {filteredSubmissions.length === 0 ? (
            <div className="mt-8 text-center py-16 border border-dashed border-[#E5E5E5] rounded-2xl bg-[#F7F7F7]">
              <FileText className="w-8 h-8 text-neutral-300 mx-auto mb-2" />
              <p className="text-xs text-neutral-600 font-semibold">No submissions recorded yet.</p>
              <p className="text-[11px] text-[#737373] mt-1 max-w-sm mx-auto">
                Fill and submit any form to automatically record your submission history and download completed PDFs.
              </p>
              <button
                onClick={() => setView({ name: "dashboard" })}
                className="mt-4 px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold cursor-pointer transition-colors"
              >
                Browse Forms
              </button>
            </div>
          ) : (
            <div className="mt-6 border border-[#E5E5E5] rounded-xl overflow-hidden bg-white shadow-xs">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#F7F7F7] border-b border-[#E5E5E5] text-neutral-500 font-mono text-[11px] uppercase">
                    <tr>
                      <th className="py-3 px-4 font-semibold">Form Name</th>
                      <th className="py-3 px-4 font-semibold">Submission Date</th>
                      <th className="py-3 px-4 font-semibold">Status</th>
                      <th className="py-3 px-4 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E5E5E5]">
                    {filteredSubmissions.map((sub) => {
                      const subDate = new Date(sub.created_at).toLocaleString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      });
                      const isDownloading = downloadingId === sub.id;

                      return (
                        <tr key={sub.id} className="hover:bg-neutral-50/60 transition-colors">
                          <td className="py-3.5 px-4">
                            <div className="font-semibold text-neutral-900 truncate max-w-xs">
                              {sub.form_title || "Form"}
                            </div>
                            <div className="text-[11px] text-[#737373] font-mono">
                              Submission #{sub.id}
                            </div>
                          </td>

                          <td className="py-3.5 px-4 font-mono text-neutral-600 whitespace-nowrap">
                            {subDate}
                          </td>

                          <td className="py-3.5 px-4 whitespace-nowrap">
                            <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[10px] font-mono bg-emerald-50 text-emerald-800 border border-emerald-200">
                              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                              <span>{sub.status || "Completed"}</span>
                            </span>
                          </td>

                          <td className="py-3.5 px-4 text-right whitespace-nowrap space-x-2">
                            <button
                              type="button"
                              onClick={() => setSelectedSubmission(sub)}
                              className="inline-flex items-center space-x-1 px-2.5 py-1 border border-[#E5E5E5] hover:border-black rounded-lg text-[11px] font-medium text-neutral-700 hover:text-black transition-colors cursor-pointer"
                              title="View Details"
                            >
                              <Eye className="w-3 h-3" />
                              <span>View Details</span>
                            </button>

                            <button
                              type="button"
                              disabled={isDownloading}
                              onClick={() => handleDownloadPdf(sub)}
                              className="inline-flex items-center space-x-1.5 px-3 py-1 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-[11px] font-semibold transition-colors disabled:opacity-50 cursor-pointer shadow-xs"
                              title="Download Completed PDF Document"
                            >
                              {isDownloading ? (
                                <>
                                  <Loader2 className="w-3.5 h-3.5 animate-spin text-white" />
                                  <span>Downloading...</span>
                                </>
                              ) : (
                                <>
                                  <Download className="w-3.5 h-3.5 text-neutral-200" />
                                  <span>Download PDF</span>
                                </>
                              )}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* TAB 2: MY FORMS & TEMPLATES */}
      {!loading && !error && activeTab === "forms" && (
        <>
          {filteredForms.length === 0 ? (
            <div className="mt-8 text-center py-16 border border-dashed border-[#E5E5E5] rounded-2xl bg-[#F7F7F7]">
              <p className="text-xs text-[#737373]">No forms found matching your filter.</p>
            </div>
          ) : (
            <div className="mt-6 border border-[#E5E5E5] rounded-xl overflow-hidden bg-white shadow-xs">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-[#F7F7F7] border-b border-[#E5E5E5] text-neutral-500 font-mono text-[11px] uppercase">
                    <tr>
                      <th className="py-3 px-4 font-semibold">Form Name</th>
                      <th className="py-3 px-4 font-semibold">Status</th>
                      <th className="py-3 px-4 font-semibold">Responses</th>
                      <th className="py-3 px-4 font-semibold">Created Date</th>
                      <th className="py-3 px-4 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E5E5E5]">
                    {filteredForms.map((item) => {
                      const subs = submissionsMap[item.id] || [];
                      const hasDraft = Boolean(draftsMap[item.id]);
                      const createdDate = new Date(item.created_at).toLocaleDateString(undefined, {
                        year: "numeric",
                        month: "short",
                        day: "numeric",
                      });
                      const isOwner = item.user_id && item.user_id === Number(user?.id);
                      const canManage = user?.role === "SUPER_ADMIN" || user?.role === "ADMIN" || isOwner;

                      return (
                        <tr key={item.id} className="hover:bg-neutral-50/60 transition-colors">
                          <td className="py-3.5 px-4">
                            <div className="font-semibold text-neutral-900 truncate max-w-xs">
                              {item.title}
                            </div>
                            <div className="text-[11px] text-[#737373] truncate max-w-xs">
                              {item.description || "No description"}
                            </div>
                          </td>

                          <td className="py-3.5 px-4 whitespace-nowrap">
                            {item.is_public ? (
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-neutral-900 text-white">
                                <span>Published</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-neutral-100 text-neutral-700 border border-neutral-300">
                                <span>Draft (Private)</span>
                              </span>
                            )}
                          </td>

                          <td className="py-3.5 px-4 font-mono text-neutral-600">
                            {subs.length} {subs.length === 1 ? "response" : "responses"}
                          </td>

                          <td className="py-3.5 px-4 font-mono text-neutral-500 whitespace-nowrap">
                            {createdDate}
                          </td>

                          <td className="py-3.5 px-4 text-right whitespace-nowrap space-x-1.5">
                            <button
                              onClick={() =>
                                setView({
                                  name: "fill",
                                  formId: item.id,
                                  formTitle: item.title,
                                })
                              }
                              className="px-2.5 py-1 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-[11px] font-medium transition-colors cursor-pointer"
                              title="Voice Fill Form"
                            >
                              Voice Fill
                            </button>

                            {canManage && (
                              <button
                                onClick={() =>
                                  setView({
                                    name: "editor",
                                    formId: item.id,
                                    formTitle: item.title,
                                  })
                                }
                                className="px-2.5 py-1 border border-[#E5E5E5] hover:border-black rounded-lg text-[11px] font-medium text-neutral-700 hover:text-black transition-colors cursor-pointer"
                                title="Edit Form Structure"
                              >
                                Edit
                              </button>
                            )}

                            <button
                              onClick={() =>
                                setView({
                                  name: "submissions",
                                  formId: item.id,
                                  formTitle: item.title,
                                })
                              }
                              className="px-2.5 py-1 border border-[#E5E5E5] hover:border-black rounded-lg text-[11px] text-neutral-700 transition-colors cursor-pointer"
                              title="View Responses"
                            >
                              Responses
                            </button>

                            <button
                              onClick={() => handleExportFormJson(item)}
                              className="p-1.5 border border-[#E5E5E5] hover:bg-neutral-100 rounded-lg text-neutral-500 hover:text-black transition-colors cursor-pointer"
                              title="Export as JSON"
                            >
                              <Download className="w-3 h-3" />
                            </button>

                            {(user?.role === "SUPER_ADMIN" || isOwner) && (
                              <button
                                onClick={() => {
                                  setDeleteFormTarget(item);
                                  setConfirmDeleteSubmissionsChecked(false);
                                }}
                                className="p-1.5 text-neutral-400 hover:text-red-600 rounded-lg hover:bg-red-50 transition-colors cursor-pointer"
                                title="Delete Form"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* TAB 3: DRAFTS */}
      {!loading && !error && activeTab === "drafts" && (
        <div className="mt-6">
          {Object.keys(draftsMap).length === 0 ? (
            <div className="text-center py-16 border border-dashed border-[#E5E5E5] rounded-2xl bg-[#F7F7F7]">
              <Clock className="w-8 h-8 text-neutral-300 mx-auto mb-2" />
              <p className="text-xs text-neutral-600 font-semibold">No saved drafts found.</p>
              <p className="text-[11px] text-[#737373] mt-1">
                When you fill a form partially and save, drafts will appear here for fast resumption.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
              {Object.entries(draftsMap).map(([formId, draft]) => (
                <div
                  key={formId}
                  className="bg-white border border-[#E5E5E5] rounded-xl p-5 shadow-xs flex flex-col justify-between"
                >
                  <div>
                    <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-amber-50 text-amber-800 border border-amber-200">
                      <Clock className="w-3 h-3 text-amber-600" />
                      <span>Draft Saved</span>
                    </span>
                    <h3 className="text-sm font-semibold text-neutral-900 mt-2 truncate">
                      {draft.formTitle || `Form #${formId}`}
                    </h3>
                    <p className="text-[11px] text-[#737373] mt-1 font-mono">
                      Last edited: {new Date(draft.updatedAt || Date.now()).toLocaleDateString()}
                    </p>
                  </div>

                  <div className="mt-5 pt-3 border-t border-[#E5E5E5] flex items-center justify-between">
                    <button
                      onClick={() => {
                        storageService.deleteDraft(formId, user?.id);
                        setDraftsMap(storageService.getDrafts(user?.id));
                        toast("Draft deleted.", "info");
                      }}
                      className="text-[11px] text-red-600 hover:underline cursor-pointer"
                    >
                      Discard
                    </button>
                    <button
                      onClick={() =>
                        setView({
                          name: "fill",
                          formId: Number(formId),
                          formTitle: draft.formTitle,
                        })
                      }
                      className="px-3 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold cursor-pointer transition-colors"
                    >
                      Resume Filling
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* VIEW DETAILS MODAL */}
      <Modal
        isOpen={Boolean(selectedSubmission)}
        onClose={() => setSelectedSubmission(null)}
        title={`Submission Details #${selectedSubmission?.id}`}
      >
        {selectedSubmission && (
          <div className="text-left text-xs space-y-4">
            <div className="p-3.5 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl space-y-2 font-mono text-[11px]">
              <div className="flex justify-between">
                <span className="text-neutral-500">Form:</span>
                <span className="font-semibold text-neutral-900">{selectedSubmission.form_title}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Submission ID:</span>
                <span className="text-neutral-900">#{selectedSubmission.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Submitted At:</span>
                <span className="text-neutral-900">
                  {new Date(selectedSubmission.created_at).toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Status:</span>
                <span className="text-emerald-700 font-semibold">{selectedSubmission.status || "Completed"}</span>
              </div>
            </div>

            <div>
              <h4 className="font-semibold text-neutral-900 text-xs mb-2">
                Submitted Responses ({Object.keys(selectedSubmission.response_json || {}).length} fields):
              </h4>
              <div className="max-h-60 overflow-y-auto space-y-2 pr-1">
                {Object.entries(selectedSubmission.response_json || {}).map(([key, val]) => (
                  <div
                    key={key}
                    className="p-2.5 bg-white border border-[#E5E5E5] rounded-lg text-xs"
                  >
                    <span className="block text-[11px] font-mono text-neutral-500">{key}:</span>
                    <span className="block font-semibold text-neutral-900 mt-0.5 break-words">
                      {typeof val === "boolean"
                        ? val
                          ? "Yes / Checked"
                          : "No / Unchecked"
                        : String(val || "—")}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-3 border-t border-[#E5E5E5] flex items-center justify-end space-x-2">
              <button
                type="button"
                onClick={() => setSelectedSubmission(null)}
                className="px-3 py-1.5 border border-[#E5E5E5] hover:bg-neutral-50 text-neutral-700 rounded-lg text-xs font-medium cursor-pointer"
              >
                Close
              </button>
              <button
                type="button"
                disabled={downloadingId === selectedSubmission.id}
                onClick={() => handleDownloadPdf(selectedSubmission)}
                className="inline-flex items-center space-x-1.5 px-4 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold cursor-pointer disabled:opacity-50"
              >
                {downloadingId === selectedSubmission.id ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Downloading...</span>
                  </>
                ) : (
                  <>
                    <Download className="w-3.5 h-3.5" />
                    <span>Download PDF</span>
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Delete Form Confirmation Modal */}
      <Modal
        isOpen={Boolean(deleteFormTarget)}
        onClose={() => {
          if (!deleting) {
            setDeleteFormTarget(null);
            setConfirmDeleteSubmissionsChecked(false);
          }
        }}
        title="Delete Form"
      >
        <div className="text-left text-xs text-neutral-700 space-y-3">
          <p>
            Are you sure you want to permanently delete the form{" "}
            <strong className="text-neutral-900 font-semibold break-words">
              &quot;{deleteFormTarget?.title}&quot;
            </strong>
            ?
          </p>
          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-amber-900 text-[11px] space-y-2">
            <p className="font-semibold text-amber-950">Permanent Deletion Warning</p>
            <p>
              Deleting this form permanently removes its structure and all associated user submissions, drafts, and generated PDFs from SQLite.
            </p>
            <label className="flex items-start space-x-2 pt-1 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={confirmDeleteSubmissionsChecked}
                onChange={(e) => setConfirmDeleteSubmissionsChecked(e.target.checked)}
                className="mt-0.5 rounded border-amber-400 text-red-600 focus:ring-red-500 w-3.5 h-3.5 cursor-pointer shrink-0"
              />
              <span className="font-medium text-amber-950 leading-tight">
                I understand and confirm permanent deletion of this form and all associated responses
              </span>
            </label>
          </div>
          <div className="pt-3 flex justify-end space-x-2">
            <button
              disabled={deleting}
              onClick={() => {
                setDeleteFormTarget(null);
                setConfirmDeleteSubmissionsChecked(false);
              }}
              className="px-3 py-1.5 border border-[#E5E5E5] rounded-lg text-xs font-medium text-neutral-700 hover:bg-neutral-50 transition-colors cursor-pointer disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              disabled={deleting || !confirmDeleteSubmissionsChecked}
              onClick={confirmDeleteForm}
              className="px-3.5 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer shadow-xs flex items-center space-x-1.5"
            >
              {deleting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Deleting...</span>
                </>
              ) : (
                <span>Delete Form</span>
              )}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
