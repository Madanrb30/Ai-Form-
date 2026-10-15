import React, { useEffect, useState, useCallback } from "react";
import {
  ShieldAlert,
  Users,
  UserCheck,
  UserX,
  Activity,
  Search,
  Filter,
  RotateCcw,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
} from "lucide-react";
import { api } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import Modal from "../components/common/Modal";

export default function AdminDashboardPage({ setView }) {
  const { user, isAdmin, isSuperAdmin } = useAuth();
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState("overview"); // "overview" | "users" | "audit"

  // Overview Stats State
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [statsError, setStatsError] = useState(null);

  // Users Management State
  const [users, setUsers] = useState([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersPage, setUsersPage] = useState(1);
  const [usersTotalPages, setUsersTotalPages] = useState(1);
  const [usersLimit] = useState(10);
  const [searchQuery, setSearchQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [usersLoading, setUsersLoading] = useState(false);
  const [usersError, setUsersError] = useState(null);

  // Modals State
  const [selectedUser, setSelectedUser] = useState(null);
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);

  const [statusConfirmUser, setStatusConfirmUser] = useState(null);
  const [statusReason, setStatusReason] = useState("");
  const [statusUpdating, setStatusUpdating] = useState(false);

  // Audit Logs State
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [auditPage, setAuditPage] = useState(1);
  const [auditTotalPages, setAuditTotalPages] = useState(1);
  const [auditLimit] = useState(15);
  const [auditActionFilter, setAuditActionFilter] = useState("ALL");
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditError, setAuditError] = useState(null);
  const [selectedAuditLog, setSelectedAuditLog] = useState(null);

  // 1. Fetch Overview Statistics
  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    setStatsError(null);
    try {
      const data = await api.getAdminStats();
      setStats(data);
    } catch (err) {
      setStatsError(err.message || "Failed to load administrative statistics.");
    } finally {
      setStatsLoading(false);
    }
  }, []);

  // 2. Fetch Users List
  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    setUsersError(null);
    try {
      const params = {
        page: usersPage,
        limit: usersLimit,
      };
      if (searchQuery.trim()) params.search = searchQuery.trim();
      if (roleFilter !== "ALL") params.role = roleFilter;
      if (statusFilter !== "ALL") params.status = statusFilter;

      const data = await api.getAdminUsers(params);
      setUsers(data.items || []);
      setUsersTotal(data.total || 0);
      setUsersTotalPages(data.total_pages || 1);
    } catch (err) {
      setUsersError(err.message || "Failed to load users list.");
    } finally {
      setUsersLoading(false);
    }
  }, [usersPage, usersLimit, searchQuery, roleFilter, statusFilter]);

  // 3. Fetch Audit Logs
  const loadAuditLogs = useCallback(async () => {
    setAuditLoading(true);
    setAuditError(null);
    try {
      const params = {
        page: auditPage,
        limit: auditLimit,
      };
      if (auditActionFilter !== "ALL") params.action = auditActionFilter;

      const data = await api.getAdminAuditLogs(params);
      setAuditLogs(data.items || []);
      setAuditTotal(data.total || 0);
      setAuditTotalPages(data.total_pages || 1);
    } catch (err) {
      setAuditError(err.message || "Failed to load audit logs.");
    } finally {
      setAuditLoading(false);
    }
  }, [auditPage, auditLimit, auditActionFilter]);

  useEffect(() => {
    if (isAdmin) {
      if (activeTab === "overview") {
        loadStats();
        // Also fetch a short preview of recent audit logs for the overview tab
        loadAuditLogs();
      } else if (activeTab === "users") {
        loadUsers();
      } else if (activeTab === "audit") {
        loadAuditLogs();
      }
    }
  }, [isAdmin, activeTab, loadStats, loadUsers, loadAuditLogs]);

  // Handle Account Status Change (Suspend / Reactivate)
  const handleConfirmStatusChange = async () => {
    if (!statusConfirmUser) return;
    setStatusUpdating(true);
    const newStatus = !statusConfirmUser.is_active;

    try {
      await api.updateUserStatus(
        statusConfirmUser.id,
        newStatus,
        statusReason.trim() || (newStatus ? "Reactivated by admin" : "Suspended by admin")
      );
      toast(
        `User ${statusConfirmUser.email} has been successfully ${newStatus ? "reactivated" : "suspended"}.`,
        "success"
      );
      setStatusConfirmUser(null);
      setStatusReason("");
      loadUsers();
      loadStats();
    } catch (err) {
      toast(`Action failed: ${err.message}`, "error");
    } finally {
      setStatusUpdating(false);
    }
  };

  // ACCESS CONTROL: Enforce ADMIN or SUPER_ADMIN access
  if (!isAdmin) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-24 text-center">
        <div className="w-16 h-16 rounded-2xl bg-neutral-900 border border-neutral-800 flex items-center justify-center mx-auto mb-6 shadow-sm">
          <ShieldAlert className="w-8 h-8 text-neutral-200" />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-neutral-900">
          Access Denied
        </h1>
        <p className="text-xs text-[#737373] mt-2 max-w-md mx-auto">
          You do not have administrative permissions to view this console. This area is strictly restricted to authorized Administrators and Super Administrators.
        </p>
        <div className="mt-6 flex justify-center space-x-3">
          <button
            onClick={() => setView({ name: "dashboard" })}
            className="px-4 py-2 bg-[#111111] hover:bg-neutral-800 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer"
          >
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-8 py-8 text-left space-y-8">
      {/* Top Console Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-[#E5E5E5] gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wide uppercase bg-neutral-900 text-white">
              {isSuperAdmin ? "Super Admin Tier" : "Admin Tier"}
            </span>
            <span className="text-xs text-neutral-400 font-mono">
              Actor: {user?.email}
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900 mt-1">
            Administration Console
          </h1>
          <p className="text-xs text-[#737373] mt-0.5">
            Manage registered accounts, inspect authorization boundaries, and review immutable audit events.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="inline-flex rounded-lg border border-[#E5E5E5] p-1 bg-[#F7F7F7]">
          <button
            onClick={() => setActiveTab("overview")}
            className={`px-3.5 py-1.5 rounded-md text-xs font-medium transition-all cursor-pointer ${
              activeTab === "overview"
                ? "bg-white text-black shadow-xs font-semibold"
                : "text-neutral-600 hover:text-black"
            }`}
          >
            Overview
          </button>
          <button
            onClick={() => setActiveTab("users")}
            className={`px-3.5 py-1.5 rounded-md text-xs font-medium transition-all cursor-pointer ${
              activeTab === "users"
                ? "bg-white text-black shadow-xs font-semibold"
                : "text-neutral-600 hover:text-black"
            }`}
          >
            User Management
          </button>
          <button
            onClick={() => setActiveTab("audit")}
            className={`px-3.5 py-1.5 rounded-md text-xs font-medium transition-all cursor-pointer ${
              activeTab === "audit"
                ? "bg-white text-black shadow-xs font-semibold"
                : "text-neutral-600 hover:text-black"
            }`}
          >
            Audit Logs
          </button>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: OVERVIEW & AGGREGATE STATISTICS */}
      {/* ========================================================================= */}
      {activeTab === "overview" && (
        <div className="space-y-8">
          {/* Stats Bar */}
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-neutral-900 uppercase tracking-wider font-mono">
              System Overview & Metrics
            </h2>
            <button
              onClick={() => {
                loadStats();
                loadAuditLogs();
              }}
              disabled={statsLoading}
              className="inline-flex items-center space-x-1.5 text-xs text-neutral-600 hover:text-black transition-colors cursor-pointer"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${statsLoading ? "animate-spin" : ""}`} />
              <span>Refresh Stats</span>
            </button>
          </div>

          {statsError && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between">
              <span>{statsError}</span>
              <button
                onClick={loadStats}
                className="underline font-semibold hover:text-red-900"
              >
                Retry
              </button>
            </div>
          )}

          {statsLoading && !stats ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="h-28 bg-[#F7F7F7] border border-[#E5E5E5] rounded-2xl animate-pulse"
                />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Total Users */}
              <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-neutral-500 mb-2">
                  <span className="text-xs font-medium">Registered Accounts</span>
                  <Users className="w-4 h-4 text-neutral-700" />
                </div>
                <div className="text-2xl font-bold font-mono tracking-tight text-neutral-900">
                  {stats?.total_users ?? 0}
                </div>
                <p className="text-[11px] text-neutral-500 mt-1">
                  Total identities in SQLite database
                </p>
              </div>

              {/* Active Users */}
              <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-emerald-600 mb-2">
                  <span className="text-xs font-medium">Active Accounts</span>
                  <UserCheck className="w-4 h-4" />
                </div>
                <div className="text-2xl font-bold font-mono tracking-tight text-neutral-900">
                  {stats?.active_users ?? 0}
                </div>
                <p className="text-[11px] text-emerald-700 mt-1">
                  Permitted to access protected APIs
                </p>
              </div>

              {/* Suspended Users */}
              <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-red-600 mb-2">
                  <span className="text-xs font-medium">Suspended Accounts</span>
                  <UserX className="w-4 h-4" />
                </div>
                <div className="text-2xl font-bold font-mono tracking-tight text-neutral-900">
                  {stats?.suspended_users ?? 0}
                </div>
                <p className="text-[11px] text-red-700 mt-1">
                  Access blocked via token revocation
                </p>
              </div>

              {/* Audit Events */}
              <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-neutral-500 mb-2">
                  <span className="text-xs font-medium">Security Audit Logs</span>
                  <Activity className="w-4 h-4 text-neutral-700" />
                </div>
                <div className="text-2xl font-bold font-mono tracking-tight text-neutral-900">
                  {stats?.total_audit_logs ?? 0}
                </div>
                <p className="text-[11px] text-neutral-500 mt-1">
                  Immutable privileged events recorded
                </p>
              </div>
            </div>
          )}

          {/* Role Distribution Breakdown */}
          {stats?.users_by_role && (
            <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs">
              <h3 className="text-xs font-semibold text-neutral-900 uppercase tracking-wider font-mono mb-4">
                Role Distribution Breakdown
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-mono">
                <div className="p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-neutral-500 block text-[11px]">USER Role</span>
                    <span className="font-bold text-neutral-900 text-sm">
                      {stats.users_by_role["USER"] ?? 0}
                    </span>
                  </div>
                  <span className="text-[10px] text-neutral-400 font-sans">Standard tier</span>
                </div>

                <div className="p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-neutral-500 block text-[11px]">ADMIN Role</span>
                    <span className="font-bold text-neutral-900 text-sm">
                      {stats.users_by_role["ADMIN"] ?? 0}
                    </span>
                  </div>
                  <span className="text-[10px] text-neutral-400 font-sans">Operational tier</span>
                </div>

                <div className="p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-neutral-500 block text-[11px]">SUPER_ADMIN Role</span>
                    <span className="font-bold text-neutral-900 text-sm">
                      {stats.users_by_role["SUPER_ADMIN"] ?? 0}
                    </span>
                  </div>
                  <span className="text-[10px] text-neutral-400 font-sans">Privileged tier</span>
                </div>
              </div>
            </div>
          )}

          {/* Recent Administrative Activity Preview */}
          <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-semibold text-neutral-900 uppercase tracking-wider font-mono">
                  Recent Administrative Events
                </h3>
                <p className="text-[11px] text-neutral-500 mt-0.5">
                  Latest privileged operations stored in SQLite audit trail
                </p>
              </div>
              <button
                onClick={() => setActiveTab("audit")}
                className="text-xs font-medium text-black hover:underline cursor-pointer"
              >
                View Full Audit Logs →
              </button>
            </div>

            {auditLoading && auditLogs.length === 0 ? (
              <div className="py-8 text-center text-xs text-neutral-400 font-mono">
                Loading recent events...
              </div>
            ) : auditLogs.length === 0 ? (
              <div className="py-8 text-center text-xs text-neutral-500 font-mono">
                No administrative activity recorded yet.
              </div>
            ) : (
              <div className="divide-y divide-[#E5E5E5] text-xs">
                {auditLogs.slice(0, 5).map((log) => (
                  <div key={log.id} className="py-3 flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                          log.status === "SUCCESS"
                            ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                            : "bg-red-50 text-red-800 border border-red-200"
                        }`}
                      >
                        {log.status}
                      </span>
                      <span className="font-mono font-medium text-neutral-900">
                        {log.action}
                      </span>
                      <span className="text-neutral-400 font-mono text-[11px]">
                        Actor: {log.actor_email || `ID #${log.actor_id}`}
                      </span>
                    </div>
                    <span className="text-neutral-400 font-mono text-[11px]">
                      {new Date(log.created_at).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: USER MANAGEMENT */}
      {/* ========================================================================= */}
      {activeTab === "users" && (
        <div className="space-y-6">
          {/* Controls: Search & Filters */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-[#F7F7F7] p-4 rounded-2xl border border-[#E5E5E5]">
            {/* Search Input */}
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setUsersPage(1);
                }}
                placeholder="Search by name or email address..."
                className="w-full pl-9 pr-3 py-1.5 bg-white border border-[#E5E5E5] rounded-lg text-xs placeholder:text-neutral-400 focus:outline-none focus:border-black font-sans"
              />
            </div>

            {/* Filter by Role */}
            <div className="flex items-center space-x-2">
              <Filter className="w-3.5 h-3.5 text-neutral-400" />
              <select
                value={roleFilter}
                onChange={(e) => {
                  setRoleFilter(e.target.value);
                  setUsersPage(1);
                }}
                className="bg-white border border-[#E5E5E5] rounded-lg px-2.5 py-1.5 text-xs text-neutral-800 focus:outline-none focus:border-black cursor-pointer font-sans"
              >
                <option value="ALL">All Roles</option>
                <option value="USER">USER</option>
                <option value="ADMIN">ADMIN</option>
                <option value="SUPER_ADMIN">SUPER_ADMIN</option>
              </select>

              {/* Filter by Status */}
              <select
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setUsersPage(1);
                }}
                className="bg-white border border-[#E5E5E5] rounded-lg px-2.5 py-1.5 text-xs text-neutral-800 focus:outline-none focus:border-black cursor-pointer font-sans"
              >
                <option value="ALL">All Statuses</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
              </select>

              <button
                onClick={loadUsers}
                className="p-1.5 bg-white border border-[#E5E5E5] rounded-lg hover:border-black text-neutral-700 transition-colors cursor-pointer"
                title="Refresh user list"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${usersLoading ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>

          {usersError && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between">
              <span>{usersError}</span>
              <button onClick={loadUsers} className="underline font-semibold hover:text-red-900">
                Retry
              </button>
            </div>
          )}

          {/* Users Table */}
          <div className="bg-white border border-[#E5E5E5] rounded-2xl overflow-hidden shadow-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-[#F7F7F7] border-b border-[#E5E5E5] text-[11px] font-mono text-neutral-500 uppercase">
                    <th className="py-3 px-4">User</th>
                    <th className="py-3 px-4">Role</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Registered</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E5E5E5]">
                  {usersLoading && users.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-neutral-400 font-mono">
                        Loading users...
                      </td>
                    </tr>
                  ) : users.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-neutral-500">
                        <Users className="w-8 h-8 text-neutral-300 mx-auto mb-2" />
                        <p className="font-semibold text-neutral-800">No users found</p>
                        <p className="text-[11px] text-neutral-400 mt-0.5">
                          Try adjusting search queries or role/status filters.
                        </p>
                      </td>
                    </tr>
                  ) : (
                    users.map((u) => {
                      const isSelf = u.id === user?.id;
                      const isTargetElevated = u.role === "ADMIN" || u.role === "SUPER_ADMIN";
                      const canModifyStatus = isSuperAdmin ? !isSelf : !isSelf && !isTargetElevated;

                      return (
                        <tr
                          key={u.id}
                          className="hover:bg-neutral-50/70 transition-colors"
                        >
                          {/* User Column */}
                          <td className="py-3.5 px-4">
                            <div className="flex items-center space-x-3">
                              <div className="w-8 h-8 rounded-full bg-neutral-900 text-white flex items-center justify-center font-bold font-mono text-xs shrink-0">
                                {u.avatar || u.email.slice(0, 2).toUpperCase()}
                              </div>
                              <div className="min-w-0">
                                <span className="font-semibold text-neutral-900 block truncate">
                                  {u.full_name || "—"}
                                  {isSelf && (
                                    <span className="ml-1.5 text-[10px] font-mono text-neutral-400">
                                      (You)
                                    </span>
                                  )}
                                </span>
                                <span className="text-[11px] text-neutral-500 font-mono block truncate">
                                  {u.email}
                                </span>
                                {u.title && (
                                  <span className="text-[10px] text-neutral-400 block truncate">
                                    {u.title}
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>

                          {/* Role Column */}
                          <td className="py-3.5 px-4 font-mono">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold ${
                                u.role === "SUPER_ADMIN"
                                  ? "bg-purple-50 text-purple-900 border border-purple-200"
                                  : u.role === "ADMIN"
                                  ? "bg-neutral-900 text-white"
                                  : "bg-neutral-100 text-neutral-800 border border-neutral-200"
                              }`}
                            >
                              {u.role}
                            </span>
                          </td>

                          {/* Status Column */}
                          <td className="py-3.5 px-4 font-mono">
                            {u.is_active ? (
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-600" />
                                <span>Active</span>
                              </span>
                            ) : (
                              <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-50 text-red-800 border border-red-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-red-600" />
                                <span>Suspended</span>
                              </span>
                            )}
                          </td>

                          {/* Registered Date */}
                          <td className="py-3.5 px-4 font-mono text-neutral-500 text-[11px]">
                            {new Date(u.created_at).toLocaleDateString()}
                          </td>

                          {/* Actions */}
                          <td className="py-3.5 px-4 text-right space-x-1.5">
                            {/* View Details */}
                            <button
                              onClick={() => {
                                setSelectedUser(u);
                                setDetailsModalOpen(true);
                              }}
                              className="px-2.5 py-1 bg-neutral-50 hover:bg-neutral-100 border border-[#E5E5E5] hover:border-black rounded-lg text-[11px] font-semibold text-neutral-800 transition-colors cursor-pointer"
                              title="Inspect user details"
                            >
                              Details
                            </button>

                            {/* Suspend / Reactivate Action */}
                            {u.is_active ? (
                              <button
                                onClick={() => setStatusConfirmUser(u)}
                                disabled={!canModifyStatus}
                                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-colors ${
                                  canModifyStatus
                                    ? "bg-red-50 hover:bg-red-100 text-red-700 border border-red-200 cursor-pointer"
                                    : "bg-neutral-100 text-neutral-400 border border-neutral-200 cursor-not-allowed"
                                }`}
                                title={
                                  isSelf
                                    ? "You cannot suspend your own account"
                                    : !isSuperAdmin && isTargetElevated
                                    ? "Admins cannot modify other administrators"
                                    : "Suspend this user account"
                                }
                              >
                                Suspend
                              </button>
                            ) : (
                              <button
                                onClick={() => setStatusConfirmUser(u)}
                                disabled={!canModifyStatus}
                                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold transition-colors ${
                                  canModifyStatus
                                    ? "bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 cursor-pointer"
                                    : "bg-neutral-100 text-neutral-400 border border-neutral-200 cursor-not-allowed"
                                }`}
                                title={
                                  isSelf
                                    ? "You cannot modify your own account"
                                    : !isSuperAdmin && isTargetElevated
                                    ? "Admins cannot modify other administrators"
                                    : "Reactivate this user account"
                                }
                              >
                                Reactivate
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {usersTotalPages > 1 && (
              <div className="p-4 border-t border-[#E5E5E5] bg-[#F7F7F7] flex items-center justify-between text-xs">
                <span className="text-neutral-500 font-mono">
                  Showing {users.length} of {usersTotal} users (Page {usersPage} of {usersTotalPages})
                </span>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setUsersPage((p) => Math.max(1, p - 1))}
                    disabled={usersPage <= 1 || usersLoading}
                    className="p-1.5 border border-[#E5E5E5] bg-white rounded-lg hover:border-black disabled:opacity-40 disabled:hover:border-[#E5E5E5] cursor-pointer"
                  >
                    <ChevronLeft className="w-4 h-4 text-neutral-700" />
                  </button>
                  <span className="font-mono font-semibold px-2">
                    {usersPage}
                  </span>
                  <button
                    onClick={() => setUsersPage((p) => Math.min(usersTotalPages, p + 1))}
                    disabled={usersPage >= usersTotalPages || usersLoading}
                    className="p-1.5 border border-[#E5E5E5] bg-white rounded-lg hover:border-black disabled:opacity-40 disabled:hover:border-[#E5E5E5] cursor-pointer"
                  >
                    <ChevronRight className="w-4 h-4 text-neutral-700" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: AUDIT LOG VIEWER */}
      {/* ========================================================================= */}
      {activeTab === "audit" && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-[#F7F7F7] p-4 rounded-2xl border border-[#E5E5E5]">
            <div>
              <h2 className="text-xs font-semibold text-neutral-900 uppercase tracking-wider font-mono">
                Security & Administrative Audit Trail
              </h2>
              <p className="text-[11px] text-neutral-500 mt-0.5">
                Immutable, read-only event logs recorded during privileged actions.
              </p>
            </div>

            <div className="flex items-center space-x-2">
              <Filter className="w-3.5 h-3.5 text-neutral-400" />
              <select
                value={auditActionFilter}
                onChange={(e) => {
                  setAuditActionFilter(e.target.value);
                  setAuditPage(1);
                }}
                className="bg-white border border-[#E5E5E5] rounded-lg px-2.5 py-1.5 text-xs text-neutral-800 focus:outline-none focus:border-black cursor-pointer font-sans"
              >
                <option value="ALL">All Actions</option>
                <option value="ROLE_CHANGED">ROLE_CHANGED</option>
                <option value="USER_SUSPENDED">USER_SUSPENDED</option>
                <option value="USER_REACTIVATED">USER_REACTIVATED</option>
                <option value="UNAUTHORIZED_ROLE_ACCESS_DENIED">ACCESS_DENIED</option>
              </select>

              <button
                onClick={loadAuditLogs}
                className="p-1.5 bg-white border border-[#E5E5E5] rounded-lg hover:border-black text-neutral-700 transition-colors cursor-pointer"
                title="Refresh audit logs"
              >
                <RotateCcw className={`w-3.5 h-3.5 ${auditLoading ? "animate-spin" : ""}`} />
              </button>
            </div>
          </div>

          {auditError && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between">
              <span>{auditError}</span>
              <button onClick={loadAuditLogs} className="underline font-semibold hover:text-red-900">
                Retry
              </button>
            </div>
          )}

          {/* Audit Logs Table */}
          <div className="bg-white border border-[#E5E5E5] rounded-2xl overflow-hidden shadow-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="bg-[#F7F7F7] border-b border-[#E5E5E5] text-[11px] font-mono text-neutral-500 uppercase">
                    <th className="py-3 px-4">Timestamp</th>
                    <th className="py-3 px-4">Actor</th>
                    <th className="py-3 px-4">Action</th>
                    <th className="py-3 px-4">Target</th>
                    <th className="py-3 px-4">Outcome</th>
                    <th className="py-3 px-4 text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E5E5E5]">
                  {auditLoading && auditLogs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-12 text-center text-neutral-400 font-mono">
                        Loading audit logs...
                      </td>
                    </tr>
                  ) : auditLogs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-12 text-center text-neutral-500">
                        <Activity className="w-8 h-8 text-neutral-300 mx-auto mb-2" />
                        <p className="font-semibold text-neutral-800">No audit events found</p>
                        <p className="text-[11px] text-neutral-400 mt-0.5">
                          Privileged actions will be logged here automatically.
                        </p>
                      </td>
                    </tr>
                  ) : (
                    auditLogs.map((log) => (
                      <tr key={log.id} className="hover:bg-neutral-50/70 transition-colors">
                        {/* Timestamp */}
                        <td className="py-3 px-4 font-mono text-neutral-500 text-[11px]">
                          {new Date(log.created_at).toLocaleString()}
                        </td>

                        {/* Actor */}
                        <td className="py-3 px-4 font-mono">
                          <span className="font-semibold text-neutral-900 block truncate max-w-[180px]">
                            {log.actor_email || `User #${log.actor_id || "System"}`}
                          </span>
                        </td>

                        {/* Action */}
                        <td className="py-3 px-4 font-mono">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-neutral-100 text-neutral-900 border border-neutral-200">
                            {log.action}
                          </span>
                        </td>

                        {/* Target */}
                        <td className="py-3 px-4 font-mono text-neutral-600 text-[11px]">
                          {log.target_type ? `${log.target_type} #${log.target_id}` : "—"}
                        </td>

                        {/* Outcome */}
                        <td className="py-3 px-4 font-mono">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              log.status === "SUCCESS"
                                ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                                : "bg-red-50 text-red-800 border border-red-200"
                            }`}
                          >
                            {log.status}
                          </span>
                        </td>

                        {/* Details Modal Trigger */}
                        <td className="py-3 px-4 text-right">
                          <button
                            onClick={() => setSelectedAuditLog(log)}
                            className="px-2.5 py-1 bg-neutral-50 hover:bg-neutral-100 border border-[#E5E5E5] hover:border-black rounded-lg text-[11px] font-semibold text-neutral-800 transition-colors cursor-pointer"
                          >
                            Inspect
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination Controls */}
            {auditTotalPages > 1 && (
              <div className="p-4 border-t border-[#E5E5E5] bg-[#F7F7F7] flex items-center justify-between text-xs">
                <span className="text-neutral-500 font-mono">
                  Showing {auditLogs.length} of {auditTotal} events (Page {auditPage} of {auditTotalPages})
                </span>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setAuditPage((p) => Math.max(1, p - 1))}
                    disabled={auditPage <= 1 || auditLoading}
                    className="p-1.5 border border-[#E5E5E5] bg-white rounded-lg hover:border-black disabled:opacity-40 disabled:hover:border-[#E5E5E5] cursor-pointer"
                  >
                    <ChevronLeft className="w-4 h-4 text-neutral-700" />
                  </button>
                  <span className="font-mono font-semibold px-2">
                    {auditPage}
                  </span>
                  <button
                    onClick={() => setAuditPage((p) => Math.min(auditTotalPages, p + 1))}
                    disabled={auditPage >= auditTotalPages || auditLoading}
                    className="p-1.5 border border-[#E5E5E5] bg-white rounded-lg hover:border-black disabled:opacity-40 disabled:hover:border-[#E5E5E5] cursor-pointer"
                  >
                    <ChevronRight className="w-4 h-4 text-neutral-700" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL 1: USER DETAILS INSPECTOR */}
      {/* ========================================================================= */}
      <Modal
        isOpen={detailsModalOpen}
        onClose={() => {
          setDetailsModalOpen(false);
          setSelectedUser(null);
        }}
        title="User Account Details"
        maxWidth="max-w-md"
      >
        {selectedUser && (
          <div className="space-y-4 text-xs font-mono">
            <div className="p-3 bg-[#F7F7F7] rounded-xl border border-[#E5E5E5] space-y-2">
              <div className="flex justify-between">
                <span className="text-neutral-500">User ID:</span>
                <span className="font-bold text-neutral-900">#{selectedUser.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Email:</span>
                <span className="font-bold text-neutral-900">{selectedUser.email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Full Name:</span>
                <span className="font-semibold text-neutral-900">{selectedUser.full_name || "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Role:</span>
                <span className="font-bold text-neutral-900">{selectedUser.role}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Job Title:</span>
                <span className="font-medium text-neutral-800">{selectedUser.title || "—"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Account Status:</span>
                <span className={selectedUser.is_active ? "text-emerald-700 font-bold" : "text-red-700 font-bold"}>
                  {selectedUser.is_active ? "Active" : "Suspended"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Registered:</span>
                <span className="text-neutral-800">
                  {new Date(selectedUser.created_at).toLocaleString()}
                </span>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setDetailsModalOpen(false)}
                className="px-4 py-2 bg-neutral-900 text-white rounded-lg text-xs font-semibold cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* ========================================================================= */}
      {/* MODAL 2: SUSPEND / REACTIVATE CONFIRMATION DIALOG */}
      {/* ========================================================================= */}
      <Modal
        isOpen={Boolean(statusConfirmUser)}
        onClose={() => {
          if (!statusUpdating) {
            setStatusConfirmUser(null);
            setStatusReason("");
          }
        }}
        title={statusConfirmUser?.is_active ? "Confirm Account Suspension" : "Confirm Account Reactivation"}
        maxWidth="max-w-md"
      >
        {statusConfirmUser && (
          <div className="space-y-4 text-xs">
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-amber-900 flex items-start space-x-2.5">
              <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">
                  {statusConfirmUser.is_active
                    ? `Are you sure you want to suspend ${statusConfirmUser.email}?`
                    : `Are you sure you want to reactivate ${statusConfirmUser.email}?`}
                </p>
                <p className="text-[11px] text-amber-800 mt-0.5">
                  {statusConfirmUser.is_active
                    ? "Suspending this user will immediately revoke all active browser tokens and block API access."
                    : "Reactivating this user will allow them to log in and access permitted resources."}
                </p>
              </div>
            </div>

            <div>
              <label className="block text-neutral-600 font-medium mb-1">
                Reason / Administrative Note (Optional)
              </label>
              <input
                type="text"
                value={statusReason}
                onChange={(e) => setStatusReason(e.target.value)}
                placeholder="e.g. Terms violation or user request"
                className="w-full px-3 py-2 bg-white border border-[#E5E5E5] rounded-lg text-xs focus:outline-none focus:border-black font-sans"
              />
            </div>

            <div className="pt-2 flex justify-end space-x-2">
              <button
                type="button"
                onClick={() => {
                  setStatusConfirmUser(null);
                  setStatusReason("");
                }}
                disabled={statusUpdating}
                className="px-4 py-2 border border-[#E5E5E5] text-neutral-700 hover:bg-neutral-100 rounded-lg text-xs font-semibold cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmStatusChange}
                disabled={statusUpdating}
                className={`px-4 py-2 text-white rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                  statusConfirmUser.is_active
                    ? "bg-red-600 hover:bg-red-700"
                    : "bg-emerald-700 hover:bg-emerald-800"
                }`}
              >
                {statusUpdating
                  ? "Updating..."
                  : statusConfirmUser.is_active
                  ? "Confirm Suspension"
                  : "Confirm Reactivation"}
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* ========================================================================= */}
      {/* MODAL 3: AUDIT LOG INSPECTOR */}
      {/* ========================================================================= */}
      <Modal
        isOpen={Boolean(selectedAuditLog)}
        onClose={() => setSelectedAuditLog(null)}
        title="Audit Event Details"
        maxWidth="max-w-lg"
      >
        {selectedAuditLog && (
          <div className="space-y-4 text-xs font-mono">
            <div className="p-3 bg-[#F7F7F7] rounded-xl border border-[#E5E5E5] space-y-2">
              <div className="flex justify-between">
                <span className="text-neutral-500">Event ID:</span>
                <span className="font-bold text-neutral-900">#{selectedAuditLog.id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Action:</span>
                <span className="font-bold text-neutral-900">{selectedAuditLog.action}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Actor:</span>
                <span className="text-neutral-900">{selectedAuditLog.actor_email || `ID #${selectedAuditLog.actor_id}`}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Target:</span>
                <span className="text-neutral-900">
                  {selectedAuditLog.target_type} #{selectedAuditLog.target_id || "N/A"}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Status:</span>
                <span className={selectedAuditLog.status === "SUCCESS" ? "text-emerald-700 font-bold" : "text-red-700 font-bold"}>
                  {selectedAuditLog.status}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">IP Address:</span>
                <span className="text-neutral-900">{selectedAuditLog.ip_address || "Internal / Loopback"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Timestamp:</span>
                <span className="text-neutral-900">{new Date(selectedAuditLog.created_at).toLocaleString()}</span>
              </div>
            </div>

            {selectedAuditLog.details && (
              <div>
                <span className="block text-neutral-500 mb-1 text-[11px]">Event Details (JSON):</span>
                <pre className="p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl text-[11px] overflow-x-auto whitespace-pre-wrap break-all text-neutral-800">
                  {selectedAuditLog.details}
                </pre>
              </div>
            )}

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setSelectedAuditLog(null)}
                className="px-4 py-2 bg-neutral-900 text-white rounded-lg text-xs font-semibold cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
