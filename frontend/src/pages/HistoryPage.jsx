import React, { useEffect, useState } from "react";
import {
  History,
  Search,
  Filter,
  CheckCircle2,
  Clock,
  Download,
  Trash2,
  Mic,
  ArrowRight,
  FileText,
  Eye,
  Edit3,
  Loader2,
} from "lucide-react";
import { api } from "../services/api";
import { storageService } from "../services/storageService";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import Modal from "../components/common/Modal";

export default function HistoryPage({ setView }) {
  const { user } = useAuth();
  const { toast } = useToast();

  const [forms, setForms] = useState([]);
  const [submissionsMap, setSubmissionsMap] = useState({});
  const [draftsMap, setDraftsMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Tab & Filters
  const [activeTab, setActiveTab] = useState("all"); // 'all' | 'completed' | 'drafts'
  const [search, setSearch] = useState("");
  const [sortOrder, setSortOrder] = useState("newest"); // 'newest' | 'oldest'

  // Delete modal
  const [deleteFormTarget, setDeleteFormTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmDeleteSubmissionsChecked, setConfirmDeleteSubmissionsChecked] = useState(false);

  const loadHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const formsList = await api.getForms();
      setForms(formsList);

      const localDrafts = storageService.getDrafts(user?.id);
      setDraftsMap(localDrafts);

      // Fetch submissions for all forms
      const subMap = {};
      for (const f of formsList) {
        try {
          const subs = await api.getSubmissions(f.id);
          subMap[f.id] = subs;
        } catch {
          subMap[f.id] = [];
        }
      }
      setSubmissionsMap(subMap);
    } catch (err) {
      setError(err.message || "Failed to load history.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
  }, [user?.id]);

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
      loadHistory();
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

  // Filter & Sort Logic
  const filteredForms = forms
    .filter((f) => {
      // Tab filter
      const subs = submissionsMap[f.id] || [];
      const hasDraft = Boolean(draftsMap[f.id]);

      if (activeTab === "completed" && subs.length === 0) return false;
      if (activeTab === "drafts" && !hasDraft) return false;

      // Text Search
      if (search) {
        const q = search.toLowerCase();
        return f.title.toLowerCase().includes(q) || (f.description && f.description.toLowerCase().includes(q));
      }
      return true;
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
            Form History
          </h1>
        </div>
        <p className="text-xs text-[#737373] mt-1">
          View and manage all your filled forms, drafts, and responses recorded in SQLite.
        </p>
      </div>

      {/* Tabs and Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mt-6 border-b border-[#E5E5E5] pb-4">
        {/* Tabs */}
        <div className="flex space-x-2">
          <button
            onClick={() => setActiveTab("all")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "all"
                ? "bg-[#111111] text-white"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            All Forms ({forms.length})
          </button>
          <button
            onClick={() => setActiveTab("completed")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "completed"
                ? "bg-[#111111] text-white"
                : "text-neutral-600 hover:bg-neutral-100"
            }`}
          >
            Completed
          </button>
          <button
            onClick={() => setActiveTab("drafts")}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "drafts"
                ? "bg-[#111111] text-white"
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
              placeholder="Search by name..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-8 pr-3 py-1.5 text-xs bg-[#F7F7F7] border border-[#E5E5E5] rounded-lg focus:bg-white focus:outline-none focus:border-neutral-900 w-48 transition-all"
            />
          </div>

          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
            className="px-2.5 py-1.5 text-xs bg-[#F7F7F7] border border-[#E5E5E5] rounded-lg focus:outline-none text-neutral-700"
          >
            <option value="newest">Newest First</option>
            <option value="oldest">Oldest First</option>
          </select>
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="py-20 text-center">
          <div className="inline-block w-6 h-6 border-2 border-neutral-900 border-t-transparent rounded-full animate-spin" />
          <p className="text-xs text-[#737373] mt-2 font-mono">Loading history records...</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex justify-between items-center">
          <span>{error}</span>
          <button onClick={loadHistory} className="underline font-semibold ml-4">
            Retry
          </button>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && filteredForms.length === 0 && (
        <div className="mt-8 text-center py-16 border border-dashed border-[#E5E5E5] rounded-2xl bg-[#F7F7F7]">
          <p className="text-xs text-[#737373]">No forms found matching your filter.</p>
        </div>
      )}

      {/* Form History Table */}
      {!loading && !error && filteredForms.length > 0 && (
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
                        {subs.length > 0 ? (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-50 text-emerald-800 border border-emerald-200">
                            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                            <span>Submitted ({subs.length})</span>
                          </span>
                        ) : hasDraft ? (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-amber-50 text-amber-800 border border-amber-200">
                            <Clock className="w-3 h-3 text-amber-600" />
                            <span>Draft Saved</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-[#F7F7F7] text-neutral-600 border border-[#E5E5E5]">
                            <span>Active Form</span>
                          </span>
                        )}
                      </td>

                      <td className="py-3.5 px-4 font-mono text-neutral-600">
                        {subs.length} {subs.length === 1 ? "response" : "responses"}
                      </td>

                      <td className="py-3.5 px-4 font-mono text-neutral-500 whitespace-nowrap">
                        {createdDate}
                      </td>

                      <td className="py-3.5 px-4 text-right whitespace-nowrap space-x-1">
                        <button
                          onClick={() =>
                            setView({
                              name: "fill",
                              formId: item.id,
                              formTitle: item.title,
                            })
                          }
                          className="px-2.5 py-1 bg-[#111111] hover:bg-neutral-800 text-white rounded text-[11px] font-medium transition-colors cursor-pointer"
                          title="Voice Fill Form"
                        >
                          Voice Fill
                        </button>

                        <button
                          onClick={() =>
                            setView({
                              name: "submissions",
                              formId: item.id,
                              formTitle: item.title,
                            })
                          }
                          className="px-2 py-1 border border-[#E5E5E5] hover:border-black rounded text-[11px] text-neutral-700 transition-colors cursor-pointer"
                          title="View Responses"
                        >
                          Responses
                        </button>

                        <button
                          onClick={() => handleExportFormJson(item)}
                          className="p-1 border border-[#E5E5E5] hover:bg-neutral-100 rounded text-neutral-500 hover:text-black transition-colors cursor-pointer"
                          title="Export as JSON"
                        >
                          <Download className="w-3 h-3" />
                        </button>

                        {/* Delete button: Only SUPER_ADMIN can delete any form; regular users can only delete their own forms */}
                        {(user?.role === "SUPER_ADMIN" || (item.user_id && item.user_id === Number(user?.id))) && (
                          <button
                            onClick={() => {
                              setDeleteFormTarget(item);
                              setConfirmDeleteSubmissionsChecked(false);
                            }}
                            className="p-1 text-neutral-400 hover:text-red-600 rounded hover:bg-red-50 transition-colors cursor-pointer"
                            title={user?.role === "SUPER_ADMIN" ? "Delete Form (Super Admin)" : "Delete Form"}
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

      {/* Delete Confirmation Modal */}
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
