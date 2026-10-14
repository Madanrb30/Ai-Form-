import React, { useEffect, useState } from "react";
import { api } from "../services/api";

export default function Dashboard({ setView }) {
  const [forms, setForms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const fetchForms = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getForms();
      setForms(data);
    } catch (err) {
      setError(err.message || "Failed to load forms");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let ignore = false;
    api
      .getForms()
      .then((data) => {
        if (!ignore) setForms(data);
      })
      .catch((err) => {
        if (!ignore) setError(err.message || "Failed to load forms");
      })
      .finally(() => {
        if (!ignore) setLoading(false);
      });

    return () => {
      ignore = true;
    };
  }, []);

  const handleDelete = async (formId, title) => {
    if (!window.confirm(`Are you sure you want to delete form "${title}"? All submissions will also be deleted.`)) {
      return;
    }
    setDeletingId(formId);
    try {
      await api.deleteForm(formId);
      setForms((prev) => prev.filter((f) => f.id !== formId));
    } catch (err) {
      alert(`Could not delete form: ${err.message}`);
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-8 border-b border-zinc-200 gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-black m-0">
            Saved Forms
          </h1>
          <p className="text-sm text-zinc-500 mt-1">
            Dynamic forms generated via natural language and stored in SQLite.
          </p>
        </div>
        <button
          onClick={() => setView({ name: "generate" })}
          className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium bg-black text-white hover:bg-zinc-800 transition-colors cursor-pointer self-start sm:self-auto"
        >
          + Create New Form
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="mt-6 p-4 bg-red-50 border border-red-200 text-sm text-red-700 flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={fetchForms}
            className="underline font-semibold ml-4 hover:text-red-900"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="py-20 text-center">
          <div className="inline-block w-6 h-6 border-2 border-zinc-900 border-t-transparent rounded-full animate-spin"></div>
          <p className="text-xs text-zinc-500 mt-2 font-mono">Loading saved forms...</p>
        </div>
      )}

      {/* Empty State */}
      {!loading && !error && forms.length === 0 && (
        <div className="mt-12 text-center py-16 border border-dashed border-zinc-300 bg-white px-6">
          <div className="w-12 h-12 bg-zinc-100 text-zinc-400 mx-auto flex items-center justify-center text-xl font-mono mb-4">
            0
          </div>
          <h3 className="text-base font-semibold text-black">No forms created yet</h3>
          <p className="text-sm text-zinc-500 max-w-md mx-auto mt-1 mb-6">
            Describe the form you need using plain English. Our AI engine will build the schema and fields in seconds.
          </p>
          <button
            onClick={() => setView({ name: "generate" })}
            className="px-4 py-2 bg-black text-white text-sm font-medium hover:bg-zinc-800 transition-colors"
          >
            Create Your First Form
          </button>
        </div>
      )}

      {/* Forms Grid */}
      {!loading && !error && forms.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-8">
          {forms.map((form) => {
            const fieldCount = form.schema_json?.fields?.length || 0;
            const createdDate = new Date(form.created_at).toLocaleDateString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
            });

            return (
              <div
                key={form.id}
                className="border border-zinc-200 bg-white p-5 flex flex-col justify-between hover:border-zinc-400 transition-all shadow-xs text-left"
              >
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-semibold text-base text-black tracking-tight line-clamp-1">
                      {form.title}
                    </h3>
                    <span className="text-[11px] font-mono px-2 py-0.5 bg-zinc-100 text-zinc-600 shrink-0">
                      {fieldCount} {fieldCount === 1 ? "field" : "fields"}
                    </span>
                  </div>
                  {form.description && (
                    <p className="text-xs text-zinc-500 mt-1 line-clamp-2">
                      {form.description}
                    </p>
                  )}
                  <p className="text-[11px] text-zinc-400 mt-3 font-mono">
                    Created {createdDate}
                  </p>
                </div>

                <div className="mt-6 pt-4 border-t border-zinc-100 flex items-center justify-between text-xs">
                  <div className="flex space-x-2">
                    <button
                      onClick={() => setView({ name: "fill", formId: form.id })}
                      className="px-3 py-1.5 bg-black text-white font-medium hover:bg-zinc-800 transition-colors"
                    >
                      Fill Form
                    </button>
                    <button
                      onClick={() => setView({ name: "submissions", formId: form.id })}
                      className="px-3 py-1.5 border border-zinc-200 text-zinc-700 hover:border-black hover:text-black transition-colors"
                    >
                      Submissions
                    </button>
                  </div>
                  <button
                    disabled={deletingId === form.id}
                    onClick={() => handleDelete(form.id, form.title)}
                    className="text-zinc-400 hover:text-red-600 transition-colors p-1"
                    title="Delete Form"
                  >
                    {deletingId === form.id ? "Deleting..." : "Delete"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
