import React, { useEffect, useState } from "react";
import {
  FileText,
  PlusCircle,
  Mic,
  CheckCircle2,
  Clock,
  Sparkles,
  ArrowRight,
  Trash2,
  Edit3,
  FolderOpen,
} from "lucide-react";
import { api } from "../services/api";
import { storageService } from "../services/storageService";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import Modal from "../components/common/Modal";

export default function DashboardPage({ setView, searchQuery = "", setSearchQuery }) {
  const { user } = useAuth();
  const { toast } = useToast();

  const [forms, setForms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [submissionsCount, setSubmissionsCount] = useState(0);
  const [draftsCount, setDraftsCount] = useState(0);

  // Deletion modal state
  const [deleteModalForm, setDeleteModalForm] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getForms();
      setForms(data);

      // Count drafts from local storage
      const drafts = storageService.getDrafts();
      setDraftsCount(Object.keys(drafts).length);

      // Count submissions across forms
      let totalSubs = 0;
      for (const f of data.slice(0, 10)) {
        try {
          const subs = await api.getSubmissions(f.id);
          totalSubs += subs.length;
        } catch {
          // ignore individual submission count failure
        }
      }
      setSubmissionsCount(totalSubs);
    } catch (err) {
      setError(err.message || "Failed to load dashboard forms.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  const confirmDelete = async () => {
    if (!deleteModalForm) return;
    setDeleting(true);
    try {
      await api.deleteForm(deleteModalForm.id);
      storageService.deleteDraft(deleteModalForm.id);
      setForms((prev) => prev.filter((f) => f.id !== deleteModalForm.id));
      toast(`Form "${deleteModalForm.title}" deleted successfully.`, "info");
      setDeleteModalForm(null);
    } catch (err) {
      toast(`Failed to delete form: ${err.message}`, "error");
    } finally {
      setDeleting(false);
    }
  };

  // Filter forms based on search query
  const filteredForms = forms.filter((f) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      f.title?.toLowerCase().includes(q) ||
      f.description?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-8 py-8 text-left">
      {/* Welcome Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-8 border-b border-[#E5E5E5] gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
              Welcome back, {user?.name?.split(" ")[0] || "User"}
            </h1>
            <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-neutral-100 text-[11px] font-mono text-neutral-600 border border-neutral-200">
              <Sparkles className="w-3 h-3 text-neutral-700" />
              <span>Voice Ready</span>
            </span>
          </div>
          <p className="text-xs text-[#737373] mt-1">
            Let&apos;s continue filling your forms with AI.
          </p>
        </div>

        <div className="flex items-center space-x-2.5">
          <button
            onClick={() => setView({ name: "create" })}
            className="inline-flex items-center space-x-2 px-4 py-2 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-all shadow-xs cursor-pointer"
          >
            <PlusCircle className="w-4 h-4" />
            <span>Create New Form</span>
          </button>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-8">
        <div className="bg-white border border-[#E5E5E5] rounded-xl p-5 hover:border-neutral-300 transition-all shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#737373]">Total Forms</span>
            <div className="w-8 h-8 rounded-lg bg-[#F7F7F7] border border-[#E5E5E5] flex items-center justify-center">
              <FileText className="w-4 h-4 text-neutral-800" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline space-x-2">
            <span className="text-2xl font-bold tracking-tight text-neutral-900 font-mono">
              {loading ? "—" : forms.length}
            </span>
            <span className="text-[11px] text-[#737373]">in SQLite Database</span>
          </div>
        </div>

        <div className="bg-white border border-[#E5E5E5] rounded-xl p-5 hover:border-neutral-300 transition-all shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#737373]">Completed Forms</span>
            <div className="w-8 h-8 rounded-lg bg-[#F7F7F7] border border-[#E5E5E5] flex items-center justify-center">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline space-x-2">
            <span className="text-2xl font-bold tracking-tight text-neutral-900 font-mono">
              {loading ? "—" : submissionsCount}
            </span>
            <span className="text-[11px] text-emerald-700 font-medium">Submissions recorded</span>
          </div>
        </div>

        <div className="bg-white border border-[#E5E5E5] rounded-xl p-5 hover:border-neutral-300 transition-all shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-[#737373]">Draft Forms</span>
            <div className="w-8 h-8 rounded-lg bg-[#F7F7F7] border border-[#E5E5E5] flex items-center justify-center">
              <Clock className="w-4 h-4 text-neutral-500" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline space-x-2">
            <span className="text-2xl font-bold tracking-tight text-neutral-900 font-mono">
              {loading ? "—" : draftsCount}
            </span>
            <span className="text-[11px] text-[#737373]">Saved in session</span>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={loadDashboardData}
            className="underline font-semibold ml-4 hover:text-red-900 cursor-pointer"
          >
            Retry Connection
          </button>
        </div>
      )}

      {/* Section Header: Recent Forms */}
      <div className="mt-10 flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-[#E5E5E5] gap-3">
        <div>
          <h2 className="text-base font-semibold text-neutral-900 tracking-tight">
            Recent Forms
          </h2>
          <p className="text-xs text-[#737373] mt-0.5">
            Select a form to begin AI voice filling or review responses.
          </p>
        </div>

        <div className="flex items-center space-x-2">
          {searchQuery && (
            <span className="text-xs text-neutral-500 font-mono">
              Found {filteredForms.length} matches
            </span>
          )}
          <button
            onClick={() => setView({ name: "forms" })}
            className="text-xs text-neutral-600 hover:text-black flex items-center space-x-1 cursor-pointer"
          >
            <span>View All</span>
            <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Loading Skeletons */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="p-5 border border-[#E5E5E5] rounded-xl bg-white animate-pulse space-y-3"
            >
              <div className="h-4 bg-neutral-200 rounded w-1/2" />
              <div className="h-3 bg-neutral-100 rounded w-3/4" />
              <div className="h-8 bg-neutral-50 rounded mt-4" />
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && filteredForms.length === 0 && (
        <div className="mt-8 text-center py-16 border border-dashed border-[#E5E5E5] rounded-2xl bg-[#F7F7F7] px-6">
          <div className="w-12 h-12 bg-white border border-[#E5E5E5] text-neutral-400 rounded-xl mx-auto flex items-center justify-center mb-4 shadow-xs">
            <FolderOpen className="w-6 h-6 text-neutral-400" />
          </div>
          <h3 className="text-sm font-semibold text-neutral-900">
            {searchQuery ? "No matching forms found" : "No forms created yet"}
          </h3>
          <p className="text-xs text-[#737373] max-w-sm mx-auto mt-1 mb-6 leading-relaxed">
            {searchQuery
              ? `No forms match your search "${searchQuery}". Clear search or create a new form.`
              : "Generate a custom form with AI natural language, upload a document, or choose from pre-built templates."}
          </p>
          <button
            onClick={() => setView({ name: "create" })}
            className="inline-flex items-center space-x-2 px-4 py-2 bg-[#111111] text-white text-xs font-semibold rounded-lg hover:bg-neutral-800 transition-colors shadow-xs cursor-pointer"
          >
            <PlusCircle className="w-4 h-4" />
            <span>Create Your First Form</span>
          </button>
        </div>
      )}

      {/* Forms Grid */}
      {!loading && !error && filteredForms.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-6">
          {filteredForms.map((form) => {
            const fieldCount = form.schema_json?.fields?.length || 0;
            const createdDate = new Date(form.created_at).toLocaleDateString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
            });
            const hasDraft = Boolean(storageService.getDraft(form.id));

            return (
              <div
                key={form.id}
                className="group bg-white border border-[#E5E5E5] hover:border-neutral-400 rounded-xl p-5 flex flex-col justify-between transition-all duration-200 shadow-xs hover:shadow-sm"
              >
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start space-x-3 min-w-0">
                      <div className="w-8 h-8 rounded-lg bg-[#F7F7F7] border border-[#E5E5E5] flex items-center justify-center shrink-0 group-hover:bg-neutral-900 group-hover:text-white transition-colors">
                        <FileText className="w-4 h-4" />
                      </div>
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold text-neutral-900 tracking-tight truncate">
                          {form.title}
                        </h3>
                        <p className="text-[11px] text-[#737373] line-clamp-2 mt-0.5">
                          {form.description || "No description provided."}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center space-x-1.5 shrink-0">
                      {hasDraft && (
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200">
                          Draft Saved
                        </span>
                      )}
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-[#F7F7F7] text-neutral-600 border border-[#E5E5E5]">
                        {fieldCount} {fieldCount === 1 ? "field" : "fields"}
                      </span>
                    </div>
                  </div>

                  <div className="mt-4 flex items-center space-x-3 text-[11px] text-neutral-400 font-mono">
                    <span>Created: {createdDate}</span>
                    <span>•</span>
                    <span className="text-neutral-500">ID #{form.id}</span>
                  </div>
                </div>

                {/* Card Action Controls */}
                <div className="mt-5 pt-3.5 border-t border-[#E5E5E5] flex items-center justify-between">
                  <div className="flex items-center space-x-2">
                    <button
                      onClick={() =>
                        setView({
                          name: "fill",
                          formId: form.id,
                          formTitle: form.title,
                        })
                      }
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 bg-[#111111] hover:bg-neutral-800 text-white text-xs font-semibold rounded-lg transition-colors cursor-pointer shadow-2xs"
                    >
                      <Mic className="w-3.5 h-3.5 text-neutral-200" />
                      <span>Voice Fill</span>
                    </button>

                    <button
                      onClick={() =>
                        setView({
                          name: "editor",
                          formId: form.id,
                          formTitle: form.title,
                        })
                      }
                      className="inline-flex items-center space-x-1 px-2.5 py-1.5 border border-[#E5E5E5] hover:border-black text-xs text-neutral-700 hover:text-black rounded-lg transition-colors cursor-pointer"
                      title="Edit form structure"
                    >
                      <Edit3 className="w-3 h-3" />
                      <span>Edit</span>
                    </button>

                    <button
                      onClick={() =>
                        setView({
                          name: "submissions",
                          formId: form.id,
                          formTitle: form.title,
                        })
                      }
                      className="px-2.5 py-1.5 border border-[#E5E5E5] hover:border-neutral-400 text-xs text-neutral-600 rounded-lg transition-colors cursor-pointer"
                    >
                      Responses
                    </button>
                  </div>

                  <button
                    onClick={() => setDeleteModalForm(form)}
                    className="p-1.5 text-neutral-400 hover:text-red-600 rounded-md hover:bg-red-50 transition-colors cursor-pointer"
                    title="Delete Form"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={Boolean(deleteModalForm)}
        onClose={() => setDeleteModalForm(null)}
        title="Delete Form"
      >
        <div className="text-left text-xs text-neutral-700 space-y-3">
          <p>
            Are you sure you want to permanently delete the form{" "}
            <strong className="text-neutral-900 font-semibold">
              &quot;{deleteModalForm?.title}&quot;
            </strong>
            ?
          </p>
          <p className="text-neutral-500">
            All associated submissions and local drafts will also be purged from SQLite. This action cannot be undone.
          </p>
          <div className="pt-3 flex justify-end space-x-2">
            <button
              onClick={() => setDeleteModalForm(null)}
              className="px-3 py-1.5 border border-[#E5E5E5] rounded-lg text-xs font-medium text-neutral-700 hover:bg-neutral-50 cursor-pointer"
            >
              Cancel
            </button>
            <button
              disabled={deleting}
              onClick={confirmDelete}
              className="px-3.5 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-semibold transition-colors disabled:opacity-50 cursor-pointer"
            >
              {deleting ? "Deleting..." : "Delete Form"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
