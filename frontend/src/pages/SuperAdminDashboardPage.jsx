import React, { useEffect, useState, useCallback } from "react";
import {
  Crown,
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
  Server,
  Database,
  Cpu,
  KeyRound,
  CheckCircle2,
  XCircle,
  FileText,
} from "lucide-react";
import { api } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { useToast } from "../context/ToastContext";
import Modal from "../components/common/Modal";

export default function SuperAdminDashboardPage({ setView }) {
  const { user, isSuperAdmin } = useAuth();
  const { toast } = useToast();

  const [activeTab, setActiveTab] = useState("overview");

  // Statistics State
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [statsError, setStatsError] = useState(null);

  // System Health State
  const [healthData, setHealthData] = useState(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [healthError, setHealthError] = useState(null);

  // User Management State
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

  // Administrative Accounts State (Admins & Super Admins)
  const [adminUsers, setAdminUsers] = useState([]);
  const [adminUsersLoading, setAdminUsersLoading] = useState(false);
  const [adminUsersError, setAdminUsersError] = useState(null);

  // Modals State
  const [selectedUser, setSelectedUser] = useState(null);
  const [detailsModalOpen, setDetailsModalOpen] = useState(false);

  // Role Change Modal State
  const [roleModalUser, setRoleModalUser] = useState(null);
  const [targetRole, setTargetRole] = useState("ADMIN");
  const [roleUpdating, setRoleUpdating] = useState(false);

  // Status Change Modal State
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
  const [auditStatusFilter, setAuditStatusFilter] = useState("ALL");
  const [auditSearchQuery, setAuditSearchQuery] = useState("");
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
      setStatsError(err.message || "Failed to load system statistics.");
    } finally {
      setStatsLoading(false);
    }
  }, []);

  // 2. Fetch System Health & Configuration
  const loadSystemHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const data = await api.getSystemHealth();
      setHealthData(data);
    } catch (err) {
      setHealthError(err.message || "Failed to retrieve system health status.");
    } finally {
      setHealthLoading(false);
    }
  }, []);

  // 3. Fetch Users List
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

  // 4. Fetch Dedicated Administrative Accounts (ADMIN + SUPER_ADMIN)
  const loadAdminDirectory = useCallback(async () => {
    setAdminUsersLoading(true);
    setAdminUsersError(null);
    try {
      const [adminsRes, supersRes] = await Promise.all([
        api.getAdminUsers({ role: "ADMIN", limit: 50 }),
        api.getAdminUsers({ role: "SUPER_ADMIN", limit: 50 }),
      ]);
      const combined = [...(supersRes.items || []), ...(adminsRes.items || [])];
      setAdminUsers(combined);
    } catch (err) {
      setAdminUsersError(err.message || "Failed to load administrative directory.");
    } finally {
      setAdminUsersLoading(false);
    }
  }, []);

  // 5. Fetch Audit Logs with Filtering
  const loadAuditLogs = useCallback(async () => {
    setAuditLoading(true);
    setAuditError(null);
    try {
      const params = {
        page: auditPage,
        limit: auditLimit,
      };
      if (auditActionFilter !== "ALL") params.action = auditActionFilter;
      if (auditStatusFilter !== "ALL") params.status = auditStatusFilter;
      if (auditSearchQuery.trim()) params.search = auditSearchQuery.trim();

      const data = await api.getAdminAuditLogs(params);
      setAuditLogs(data.items || []);
      setAuditTotal(data.total || 0);
      setAuditTotalPages(data.total_pages || 1);
    } catch (err) {
      setAuditError(err.message || "Failed to load security audit logs.");
    } finally {
      setAuditLoading(false);
    }
  }, [auditPage, auditLimit, auditActionFilter, auditStatusFilter, auditSearchQuery]);

  // Reload data on tab switch
  useEffect(() => {
    if (isSuperAdmin) {
      if (activeTab === "overview") {
        loadStats();
        loadSystemHealth();
      } else if (activeTab === "users") {
        loadUsers();
      } else if (activeTab === "admins") {
        loadAdminDirectory();
      } else if (activeTab === "audit") {
        loadAuditLogs();
      } else if (activeTab === "health") {
        loadSystemHealth();
      }
    }
  }, [activeTab, isSuperAdmin, loadStats, loadSystemHealth, loadUsers, loadAdminDirectory, loadAuditLogs]);

  // Execute Role Change
  const handleConfirmRoleChange = async () => {
    if (!roleModalUser) return;
    setRoleUpdating(true);
    try {
      await api.updateUserRole(roleModalUser.id, targetRole);
      toast(
        `User ${roleModalUser.email} role updated to ${targetRole}. Existing sessions revoked.`,
        "success"
      );
      setRoleModalUser(null);
      loadUsers();
      loadAdminDirectory();
      loadStats();
    } catch (err) {
      toast(`Role update failed: ${err.message}`, "error");
    } finally {
      setRoleUpdating(false);
    }
  };

  // Execute Status Change (Suspend / Reactivate)
  const handleConfirmStatusChange = async () => {
    if (!statusConfirmUser) return;
    setStatusUpdating(true);
    try {
      const newStatus = !statusConfirmUser.is_active;
      await api.updateUserStatus(
        statusConfirmUser.id,
        newStatus,
        statusReason.trim() || (newStatus ? "Reactivated by Super Admin" : "Suspended by Super Admin")
      );
      toast(
        `User ${statusConfirmUser.email} has been successfully ${newStatus ? "reactivated" : "suspended"}.`,
        "success"
      );
      setStatusConfirmUser(null);
      setStatusReason("");
      loadUsers();
      loadAdminDirectory();
      loadStats();
    } catch (err) {
      toast(`Status update failed: ${err.message}`, "error");
    } finally {
      setStatusUpdating(false);
    }
  };

  // ACCESS CONTROL: Enforce SUPER_ADMIN role
  if (!isSuperAdmin) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-24 text-center">
        <div className="w-16 h-16 rounded-2xl bg-neutral-900 border border-neutral-800 flex items-center justify-center mx-auto mb-6 shadow-sm">
          <ShieldAlert className="w-8 h-8 text-neutral-200" />
        </div>
        <h1 className="text-xl font-bold tracking-tight text-neutral-900">
          Super Administrator Authorization Required
        </h1>
        <p className="text-xs text-[#737373] mt-2 max-w-md mx-auto">
          This portal contains governance controls reserved exclusively for the SUPER_ADMIN tier. Standard users and ordinary administrators are strictly restricted from accessing these services.
        </p>
        <div className="mt-6 flex justify-center space-x-3">
          <button
            onClick={() => setView({ name: "dashboard" })}
            className="px-4 py-2 bg-black text-white text-xs font-semibold rounded-lg hover:bg-neutral-800 transition-colors cursor-pointer"
          >
            Return to Dashboard
          </button>
          <button
            onClick={() => setView({ name: "admin" })}
            className="px-4 py-2 bg-neutral-100 text-neutral-800 text-xs font-semibold rounded-lg hover:bg-neutral-200 transition-colors cursor-pointer"
          >
            Open Admin Console
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8 animate-in fade-in duration-150">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-[#E5E5E5] gap-4">
        <div>
          <div className="flex items-center space-x-2.5">
            <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wide uppercase bg-neutral-950 text-white border border-neutral-800">
              <Crown className="w-3 h-3 text-amber-400" />
              <span>Super Administrator Portal</span>
            </span>
            <span className="text-xs text-neutral-400 font-mono">
              Actor: {user?.email}
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900 mt-1">
            Governance & Privilege Control
          </h1>
          <p className="text-xs text-[#737373] mt-0.5">
            Manage administrative delegations, govern role assignments, inspect system health, and review audit records.
          </p>
        </div>

        {/* Tab Switcher */}
        <div className="inline-flex rounded-lg border border-[#E5E5E5] p-1 bg-[#F7F7F7] overflow-x-auto max-w-full">
          {[
            { id: "overview", label: "Overview" },
            { id: "users", label: "User Governance" },
            { id: "admins", label: "Admin Directory" },
            { id: "audit", label: "Audit Center" },
            { id: "health", label: "System Health" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3.5 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-all cursor-pointer ${
                activeTab === tab.id
                  ? "bg-white text-black shadow-xs font-semibold"
                  : "text-neutral-600 hover:text-black"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ========================================================================= */}
      {/* TAB 1: SYSTEM OVERVIEW */}
      {/* ========================================================================= */}
      {activeTab === "overview" && (
        <div className="space-y-8">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-neutral-900 uppercase tracking-wider font-mono">
              Platform Metrics & Resource Totals
            </h2>
            <button
              onClick={() => {
                loadStats();
                loadSystemHealth();
              }}
              disabled={statsLoading}
              className="inline-flex items-center space-x-1.5 text-xs text-neutral-600 hover:text-black transition-colors cursor-pointer"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${statsLoading ? "animate-spin" : ""}`} />
              <span>Refresh Metrics</span>
            </button>
          </div>

          {statsError && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between">
              <span>{statsError}</span>
              <button onClick={loadStats} className="underline font-semibold hover:text-red-900">
                Retry
              </button>
            </div>
          )}

          {statsLoading && !stats ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="h-28 bg-[#F7F7F7] border border-[#E5E5E5] rounded-2xl animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Total Users */}
              <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-neutral-500 mb-2">
                  <span className="text-xs font-medium">Total Registered Users</span>
                  <Users className="w-4 h-4 text-neutral-700" />
                </div>
                <div className="text-2xl font-bold font-mono tracking-tight text-neutral-900">
                  {stats?.total_users ?? 0}
                </div>
                <p className="text-[11px] text-neutral-500 mt-1">
                  Active database user records
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
                  Authorized to access platform APIs
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
                  Revoked tokens & blocked access
                </p>
              </div>

              {/* Total Audit Events */}
              <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
                <div className="flex items-center justify-between text-neutral-500 mb-2">
                  <span className="text-xs font-medium">Audit Events Recorded</span>
                  <Activity className="w-4 h-4 text-neutral-700" />
                </div>
                <div className="text-2xl font-bold font-mono tracking-tight text-neutral-900">
                  {stats?.total_audit_logs ?? 0}
                </div>
                <p className="text-[11px] text-neutral-500 mt-1">
                  Immutable privileged trail
                </p>
              </div>
            </div>
          )}

          {/* Secondary Stats Row: Role Breakdown & Resource Metrics */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Roles Breakdown */}
            <div className="lg:col-span-2 bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs">
              <h3 className="text-xs font-semibold text-neutral-900 uppercase tracking-wider font-mono mb-4">
                Authorization Tier Distribution
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-mono">
                <div className="p-3.5 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-neutral-500 block text-[11px]">Standard Users</span>
                    <span className="font-bold text-neutral-900 text-lg">
                      {stats?.users_by_role?.["USER"] ?? 0}
                    </span>
                  </div>
                  <span className="text-[10px] text-neutral-400 font-sans">USER tier</span>
                </div>

                <div className="p-3.5 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-neutral-500 block text-[11px]">Administrators</span>
                    <span className="font-bold text-neutral-900 text-lg">
                      {stats?.users_by_role?.["ADMIN"] ?? 0}
                    </span>
                  </div>
                  <span className="text-[10px] text-neutral-400 font-sans">ADMIN tier</span>
                </div>

                <div className="p-3.5 bg-neutral-900 text-white border border-neutral-800 rounded-xl flex items-center justify-between">
                  <div>
                    <span className="text-neutral-400 block text-[11px]">Super Administrators</span>
                    <span className="font-bold text-white text-lg">
                      {stats?.users_by_role?.["SUPER_ADMIN"] ?? 0}
                    </span>
                  </div>
                  <Crown className="w-4 h-4 text-amber-400" />
                </div>
              </div>
            </div>

            {/* Platform Resource Metrics */}
            <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs">
              <h3 className="text-xs font-semibold text-neutral-900 uppercase tracking-wider font-mono mb-4">
                Platform Workflows
              </h3>
              <div className="space-y-3 font-mono text-xs">
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-[#F7F7F7] border border-[#E5E5E5]">
                  <span className="text-neutral-600 flex items-center space-x-2">
                    <FileText className="w-3.5 h-3.5 text-neutral-500" />
                    <span>Total Created Forms</span>
                  </span>
                  <span className="font-bold text-neutral-900">
                    {stats?.total_forms ?? 0}
                  </span>
                </div>
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-[#F7F7F7] border border-[#E5E5E5]">
                  <span className="text-neutral-600 flex items-center space-x-2">
                    <CheckCircle2 className="w-3.5 h-3.5 text-neutral-500" />
                    <span>Total Submissions</span>
                  </span>
                  <span className="font-bold text-neutral-900">
                    {stats?.total_submissions ?? 0}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 2: USER GOVERNANCE (ROLE PROMOTION & SUSPENSION) */}
      {/* ========================================================================= */}
      {activeTab === "users" && (
        <div className="space-y-6">
          {/* Controls Bar */}
          <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setUsersPage(1);
                }}
                placeholder="Search accounts by name or email..."
                className="w-full pl-9 pr-4 py-2 text-xs bg-white border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 transition-colors"
              />
            </div>

            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-1.5 text-xs text-neutral-500">
                <Filter className="w-3.5 h-3.5" />
                <span>Role:</span>
                <select
                  value={roleFilter}
                  onChange={(e) => {
                    setRoleFilter(e.target.value);
                    setUsersPage(1);
                  }}
                  className="bg-white border border-[#E5E5E5] rounded-md px-2 py-1 text-xs text-neutral-900 focus:outline-none cursor-pointer"
                >
                  <option value="ALL">All Roles</option>
                  <option value="USER">USER</option>
                  <option value="ADMIN">ADMIN</option>
                  <option value="SUPER_ADMIN">SUPER_ADMIN</option>
                </select>
              </div>

              <div className="flex items-center space-x-1.5 text-xs text-neutral-500">
                <span>Status:</span>
                <select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setUsersPage(1);
                  }}
                  className="bg-white border border-[#E5E5E5] rounded-md px-2 py-1 text-xs text-neutral-900 focus:outline-none cursor-pointer"
                >
                  <option value="ALL">All Status</option>
                  <option value="active">Active</option>
                  <option value="suspended">Suspended</option>
                </select>
              </div>
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

          {/* Table */}
          <div className="bg-white border border-[#E5E5E5] rounded-2xl overflow-hidden shadow-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="bg-[#F7F7F7] border-b border-[#E5E5E5] text-neutral-500 font-mono uppercase text-[10px] tracking-wider">
                    <th className="py-3 px-4">User</th>
                    <th className="py-3 px-4">Role</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Registered</th>
                    <th className="py-3 px-4 text-right">Super Admin Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E5E5E5]">
                  {usersLoading ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-neutral-400">
                        <RotateCcw className="w-5 h-5 animate-spin mx-auto mb-2 text-neutral-300" />
                        <span>Loading user directory...</span>
                      </td>
                    </tr>
                  ) : users.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-neutral-400">
                        No user accounts match the current filter criteria.
                      </td>
                    </tr>
                  ) : (
                    users.map((u) => {
                      const isSelf = u.id === user?.id;
                      const isTargetSuper = u.role === "SUPER_ADMIN";

                      return (
                        <tr key={u.id} className="hover:bg-neutral-50/70 transition-colors">
                          <td className="py-3.5 px-4">
                            <div className="flex items-center space-x-3">
                              <div className="w-8 h-8 rounded-full bg-neutral-100 border border-neutral-200 flex items-center justify-center font-bold text-neutral-700 text-xs shrink-0">
                                {u.avatar || u.email.substring(0, 2).toUpperCase()}
                              </div>
                              <div className="min-w-0">
                                <p className="font-semibold text-neutral-900 truncate">
                                  {u.full_name || "Unnamed User"} {isSelf && <span className="text-[10px] text-neutral-400 font-mono">(You)</span>}
                                </p>
                                <p className="text-[11px] text-neutral-500 font-mono truncate">
                                  {u.email}
                                </p>
                              </div>
                            </div>
                          </td>

                          <td className="py-3.5 px-4 font-mono">
                            <span
                              className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-semibold tracking-wider uppercase border ${
                                u.role === "SUPER_ADMIN"
                                  ? "bg-neutral-900 text-white border-neutral-800"
                                  : u.role === "ADMIN"
                                  ? "bg-neutral-100 text-neutral-800 border-neutral-300 font-bold"
                                  : "bg-white text-neutral-600 border-neutral-200"
                              }`}
                            >
                              {u.role === "SUPER_ADMIN" && <Crown className="w-2.5 h-2.5 text-amber-400" />}
                              <span>{u.role}</span>
                            </span>
                          </td>

                          <td className="py-3.5 px-4 font-mono">
                            <span
                              className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${
                                u.is_active
                                  ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                                  : "bg-red-50 text-red-700 border border-red-200"
                              }`}
                            >
                              <span className={`w-1.5 h-1.5 rounded-full ${u.is_active ? "bg-emerald-500" : "bg-red-500"}`} />
                              <span>{u.is_active ? "Active" : "Suspended"}</span>
                            </span>
                          </td>

                          <td className="py-3.5 px-4 text-neutral-500 font-mono text-[11px]">
                            {u.created_at ? new Date(u.created_at).toLocaleDateString() : "—"}
                          </td>

                          <td className="py-3.5 px-4 text-right space-x-2">
                            {/* Inspect */}
                            <button
                              onClick={() => {
                                setSelectedUser(u);
                                setDetailsModalOpen(true);
                              }}
                              className="px-2 py-1 bg-white border border-[#E5E5E5] text-neutral-700 rounded hover:bg-neutral-50 text-[11px] font-medium transition-colors cursor-pointer"
                            >
                              Details
                            </button>

                            {/* Role Governance Button */}
                            <button
                              onClick={() => {
                                setRoleModalUser(u);
                                setTargetRole(u.role === "ADMIN" ? "USER" : "ADMIN");
                              }}
                              disabled={isTargetSuper}
                              title={isTargetSuper ? "Super Admin roles are governed through designated bootstrap protocols." : "Promote or demote user role"}
                              className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors cursor-pointer border ${
                                isTargetSuper
                                  ? "bg-neutral-100 text-neutral-400 border-neutral-200 cursor-not-allowed"
                                  : "bg-neutral-900 text-white border-neutral-900 hover:bg-neutral-800"
                              }`}
                            >
                              {u.role === "ADMIN" ? "Demote to USER" : u.role === "USER" ? "Promote to ADMIN" : "Manage Role"}
                            </button>

                            {/* Suspend / Reactivate */}
                            <button
                              onClick={() => setStatusConfirmUser(u)}
                              disabled={isSelf}
                              title={isSelf ? "You cannot suspend your own account" : ""}
                              className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors cursor-pointer border ${
                                isSelf
                                  ? "bg-neutral-100 text-neutral-400 border-neutral-200 cursor-not-allowed"
                                  : u.is_active
                                  ? "bg-white text-red-600 border-red-200 hover:bg-red-50"
                                  : "bg-white text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                              }`}
                            >
                              {u.is_active ? "Suspend" : "Reactivate"}
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {usersTotalPages > 1 && (
              <div className="py-3 px-4 bg-[#F7F7F7] border-t border-[#E5E5E5] flex items-center justify-between text-xs text-neutral-500 font-mono">
                <span>
                  Showing {users.length} of {usersTotal} accounts (Page {usersPage} of {usersTotalPages})
                </span>
                <div className="flex items-center space-x-1">
                  <button
                    onClick={() => setUsersPage((p) => Math.max(1, p - 1))}
                    disabled={usersPage <= 1 || usersLoading}
                    className="p-1 rounded border border-[#E5E5E5] bg-white disabled:opacity-40 hover:bg-neutral-100 cursor-pointer"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setUsersPage((p) => Math.min(usersTotalPages, p + 1))}
                    disabled={usersPage >= usersTotalPages || usersLoading}
                    className="p-1 rounded border border-[#E5E5E5] bg-white disabled:opacity-40 hover:bg-neutral-100 cursor-pointer"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 3: DEDICATED ADMIN DIRECTORY */}
      {/* ========================================================================= */}
      {activeTab === "admins" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 uppercase tracking-wider font-mono">
                Privileged Administrative Roster
              </h2>
              <p className="text-xs text-neutral-500 mt-0.5">
                Directory of all accounts with elevated permissions across the system.
              </p>
            </div>
            <button
              onClick={loadAdminDirectory}
              disabled={adminUsersLoading}
              className="inline-flex items-center space-x-1.5 text-xs text-neutral-600 hover:text-black transition-colors cursor-pointer"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${adminUsersLoading ? "animate-spin" : ""}`} />
              <span>Refresh Roster</span>
            </button>
          </div>

          {adminUsersError && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700">
              {adminUsersError}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {adminUsersLoading ? (
              [1, 2, 3].map((i) => (
                <div key={i} className="h-44 bg-[#F7F7F7] border border-[#E5E5E5] rounded-2xl animate-pulse" />
              ))
            ) : adminUsers.length === 0 ? (
              <div className="col-span-full py-12 text-center text-neutral-400 text-xs">
                No administrative accounts found.
              </div>
            ) : (
              adminUsers.map((adminAcc) => {
                const isSelf = adminAcc.id === user?.id;
                const isSuper = adminAcc.role === "SUPER_ADMIN";

                return (
                  <div
                    key={adminAcc.id}
                    className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-3">
                        <span
                          className={`inline-flex items-center space-x-1 px-2.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider uppercase border ${
                            isSuper
                              ? "bg-neutral-900 text-white border-neutral-800"
                              : "bg-neutral-100 text-neutral-900 border-neutral-300"
                          }`}
                        >
                          {isSuper && <Crown className="w-3 h-3 text-amber-400" />}
                          <span>{adminAcc.role}</span>
                        </span>

                        <span
                          className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-mono font-medium ${
                            adminAcc.is_active
                              ? "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              : "bg-red-50 text-red-700 border border-red-200"
                          }`}
                        >
                          <span>{adminAcc.is_active ? "Active" : "Suspended"}</span>
                        </span>
                      </div>

                      <div className="flex items-center space-x-3 mb-3">
                        <div className="w-10 h-10 rounded-full bg-neutral-100 border border-neutral-200 flex items-center justify-center font-bold text-neutral-800 text-sm shrink-0">
                          {adminAcc.avatar || adminAcc.email.substring(0, 2).toUpperCase()}
                        </div>
                        <div className="min-w-0">
                          <p className="font-semibold text-neutral-900 text-sm truncate">
                            {adminAcc.full_name || "Unnamed Administrator"}
                          </p>
                          <p className="text-xs text-neutral-500 font-mono truncate">
                            {adminAcc.email}
                          </p>
                        </div>
                      </div>

                      <div className="space-y-1 text-[11px] text-neutral-500 font-mono py-2 border-t border-[#F0F0F0]">
                        <p>ID: #{adminAcc.id}</p>
                        <p>Created: {new Date(adminAcc.created_at).toLocaleDateString()}</p>
                      </div>
                    </div>

                    <div className="mt-4 pt-3 border-t border-[#E5E5E5] flex items-center justify-end space-x-2">
                      <button
                        onClick={() => {
                          setSelectedUser(adminAcc);
                          setDetailsModalOpen(true);
                        }}
                        className="px-2.5 py-1 text-xs text-neutral-600 hover:text-black font-medium cursor-pointer"
                      >
                        Inspect
                      </button>

                      {!isSuper && (
                        <button
                          onClick={() => {
                            setRoleModalUser(adminAcc);
                            setTargetRole("USER");
                          }}
                          className="px-2.5 py-1 rounded text-xs font-medium bg-neutral-100 hover:bg-neutral-200 text-neutral-800 transition-colors cursor-pointer"
                        >
                          Demote to USER
                        </button>
                      )}

                      {!isSelf && (
                        <button
                          onClick={() => setStatusConfirmUser(adminAcc)}
                          className={`px-2.5 py-1 rounded text-xs font-medium border cursor-pointer ${
                            adminAcc.is_active
                              ? "text-red-600 border-red-200 hover:bg-red-50"
                              : "text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                          }`}
                        >
                          {adminAcc.is_active ? "Suspend" : "Reactivate"}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 4: SECURITY AUDIT CENTER */}
      {/* ========================================================================= */}
      {activeTab === "audit" && (
        <div className="space-y-6">
          {/* Controls Bar */}
          <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
            <div className="relative flex-1 max-w-md">
              <Search className="w-4 h-4 text-neutral-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={auditSearchQuery}
                onChange={(e) => {
                  setAuditSearchQuery(e.target.value);
                  setAuditPage(1);
                }}
                placeholder="Search audit trail by actor, action, or details..."
                className="w-full pl-9 pr-4 py-2 text-xs bg-white border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900 transition-colors"
              />
            </div>

            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-1.5 text-xs text-neutral-500">
                <Filter className="w-3.5 h-3.5" />
                <span>Action:</span>
                <select
                  value={auditActionFilter}
                  onChange={(e) => {
                    setAuditActionFilter(e.target.value);
                    setAuditPage(1);
                  }}
                  className="bg-white border border-[#E5E5E5] rounded-md px-2 py-1 text-xs text-neutral-900 focus:outline-none cursor-pointer"
                >
                  <option value="ALL">All Actions</option>
                  <option value="ROLE_CHANGED">ROLE_CHANGED</option>
                  <option value="ROLE_CHANGE_REJECTED">ROLE_CHANGE_REJECTED</option>
                  <option value="USER_SUSPENDED">USER_SUSPENDED</option>
                  <option value="USER_REACTIVATED">USER_REACTIVATED</option>
                  <option value="USER_SUSPENSION_REJECTED">USER_SUSPENSION_REJECTED</option>
                  <option value="USER_REGISTERED">USER_REGISTERED</option>
                  <option value="LOGIN_SUCCESS">LOGIN_SUCCESS</option>
                </select>
              </div>

              <div className="flex items-center space-x-1.5 text-xs text-neutral-500">
                <span>Outcome:</span>
                <select
                  value={auditStatusFilter}
                  onChange={(e) => {
                    setAuditStatusFilter(e.target.value);
                    setAuditPage(1);
                  }}
                  className="bg-white border border-[#E5E5E5] rounded-md px-2 py-1 text-xs text-neutral-900 focus:outline-none cursor-pointer"
                >
                  <option value="ALL">All Outcomes</option>
                  <option value="SUCCESS">SUCCESS</option>
                  <option value="FAILURE">FAILURE</option>
                </select>
              </div>
            </div>
          </div>

          {auditError && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700">
              {auditError}
            </div>
          )}

          {/* Audit Logs Table */}
          <div className="bg-white border border-[#E5E5E5] rounded-2xl overflow-hidden shadow-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse font-mono">
                <thead>
                  <tr className="bg-[#F7F7F7] border-b border-[#E5E5E5] text-neutral-500 uppercase text-[10px] tracking-wider font-sans">
                    <th className="py-3 px-4">Timestamp (UTC)</th>
                    <th className="py-3 px-4">Action</th>
                    <th className="py-3 px-4">Actor</th>
                    <th className="py-3 px-4">Target</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E5E5E5]">
                  {auditLoading ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-neutral-400">
                        <RotateCcw className="w-5 h-5 animate-spin mx-auto mb-2 text-neutral-300" />
                        <span>Loading audit event trail...</span>
                      </td>
                    </tr>
                  ) : auditLogs.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="py-8 text-center text-neutral-400 font-sans">
                        No security audit records match the current criteria.
                      </td>
                    </tr>
                  ) : (
                    auditLogs.map((log) => {
                      const isFailure = log.status === "FAILURE";
                      return (
                        <tr key={log.id} className="hover:bg-neutral-50/70 transition-colors">
                          <td className="py-3 px-4 text-neutral-500 text-[11px] whitespace-nowrap">
                            {new Date(log.created_at).toISOString().replace("T", " ").substring(0, 19)}
                          </td>
                          <td className="py-3 px-4 font-bold text-neutral-900 text-[11px]">
                            {log.action}
                          </td>
                          <td className="py-3 px-4 text-neutral-700 truncate max-w-[180px]">
                            {log.actor_email || `#${log.actor_id}` || "SYSTEM"}
                          </td>
                          <td className="py-3 px-4 text-neutral-600">
                            {log.target_type ? `${log.target_type} #${log.target_id || ""}` : "—"}
                          </td>
                          <td className="py-3 px-4">
                            <span
                              className={`inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-bold ${
                                isFailure
                                  ? "bg-red-50 text-red-700 border border-red-200"
                                  : "bg-emerald-50 text-emerald-700 border border-emerald-200"
                              }`}
                            >
                              {isFailure ? (
                                <XCircle className="w-3 h-3 text-red-500" />
                              ) : (
                                <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                              )}
                              <span>{log.status}</span>
                            </span>
                          </td>
                          <td className="py-3 px-4 text-right">
                            <button
                              onClick={() => setSelectedAuditLog(log)}
                              className="px-2 py-1 bg-white border border-[#E5E5E5] rounded text-neutral-700 hover:text-black hover:bg-neutral-50 text-[11px] font-sans font-medium transition-colors cursor-pointer"
                            >
                              Inspect
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {auditTotalPages > 1 && (
              <div className="py-3 px-4 bg-[#F7F7F7] border-t border-[#E5E5E5] flex items-center justify-between text-xs text-neutral-500 font-mono">
                <span>
                  Showing {auditLogs.length} of {auditTotal} events (Page {auditPage} of {auditTotalPages})
                </span>
                <div className="flex items-center space-x-1">
                  <button
                    onClick={() => setAuditPage((p) => Math.max(1, p - 1))}
                    disabled={auditPage <= 1 || auditLoading}
                    className="p-1 rounded border border-[#E5E5E5] bg-white disabled:opacity-40 hover:bg-neutral-100 cursor-pointer"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setAuditPage((p) => Math.min(auditTotalPages, p + 1))}
                    disabled={auditPage >= auditTotalPages || auditLoading}
                    className="p-1 rounded border border-[#E5E5E5] bg-white disabled:opacity-40 hover:bg-neutral-100 cursor-pointer"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* TAB 5: SYSTEM HEALTH & SETTINGS */}
      {/* ========================================================================= */}
      {activeTab === "health" && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-neutral-900 uppercase tracking-wider font-mono">
                Operational Status & Read-Only Configuration
              </h2>
              <p className="text-xs text-neutral-500 mt-0.5">
                Runtime health, database connectivity, and configured AI services.
              </p>
            </div>
            <button
              onClick={loadSystemHealth}
              disabled={healthLoading}
              className="inline-flex items-center space-x-1.5 text-xs text-neutral-600 hover:text-black transition-colors cursor-pointer"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${healthLoading ? "animate-spin" : ""}`} />
              <span>Refresh Health</span>
            </button>
          </div>

          {healthError && (
            <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700">
              {healthError}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Backend Service */}
            <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-neutral-500 mb-2">
                <span className="text-xs font-medium">Backend Application</span>
                <Server className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="text-lg font-bold font-mono tracking-tight text-neutral-900">
                {healthData?.project_name || "AI Voice Form Assistant"}
              </div>
              <p className="text-[11px] text-emerald-700 mt-1 font-mono">
                Status: {healthData?.status || "OK"} • v{healthData?.version || "1.0.0"}
              </p>
            </div>

            {/* Database Engine */}
            <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-neutral-500 mb-2">
                <span className="text-xs font-medium">Database Engine</span>
                <Database className="w-4 h-4 text-neutral-700" />
              </div>
              <div className="text-lg font-bold font-mono tracking-tight text-neutral-900">
                {healthData?.database_type || "SQLite"}
              </div>
              <p className="text-[11px] text-emerald-700 mt-1 font-mono">
                Connectivity: {healthData?.database_status || "healthy"}
              </p>
            </div>

            {/* AI Provider */}
            <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-neutral-500 mb-2">
                <span className="text-xs font-medium">AI Engine Provider</span>
                <Cpu className="w-4 h-4 text-neutral-700" />
              </div>
              <div className="text-lg font-bold font-mono tracking-tight text-neutral-900 uppercase">
                {healthData?.ai_provider || "Groq"}
              </div>
              <p className="text-[11px] text-neutral-500 mt-1 font-mono">
                Mode: {healthData?.ai_mode === "groq" ? "Cloud Production" : "Offline Demo"}
              </p>
            </div>

            {/* Authentication Protocol */}
            <div className="bg-white border border-[#E5E5E5] rounded-2xl p-5 shadow-xs">
              <div className="flex items-center justify-between text-neutral-500 mb-2">
                <span className="text-xs font-medium">Token Security</span>
                <KeyRound className="w-4 h-4 text-neutral-700" />
              </div>
              <div className="text-lg font-bold font-mono tracking-tight text-neutral-900">
                {healthData?.jwt_algorithm || "HS256"}
              </div>
              <p className="text-[11px] text-neutral-500 mt-1 font-mono">
                Expiry: {healthData?.token_expiry_hours || 168} hrs
              </p>
            </div>
          </div>

          {/* Model Configuration Details */}
          <div className="bg-white border border-[#E5E5E5] rounded-2xl p-6 shadow-xs">
            <h3 className="text-xs font-semibold text-neutral-900 uppercase tracking-wider font-mono mb-4">
              AI Models & Runtime Limits
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs font-mono">
              <div className="p-3.5 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl">
                <span className="text-neutral-500 block text-[11px]">Primary Reasoning Model</span>
                <span className="font-bold text-neutral-900 text-sm block mt-1 truncate">
                  {healthData?.ai_model || "llama-3.3-70b-versatile"}
                </span>
              </div>

              <div className="p-3.5 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl">
                <span className="text-neutral-500 block text-[11px]">Transcription Audio Model</span>
                <span className="font-bold text-neutral-900 text-sm block mt-1 truncate">
                  {healthData?.transcription_model || "whisper-large-v3-turbo"}
                </span>
              </div>

              <div className="p-3.5 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl">
                <span className="text-neutral-500 block text-[11px]">Max Audio Payload</span>
                <span className="font-bold text-neutral-900 text-sm block mt-1">
                  {healthData?.max_audio_size_mb || 25} MB (Cloud Safe)
                </span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* MODAL: ROLE CHANGE CONFIRMATION */}
      {/* ========================================================================= */}
      {roleModalUser && (
        <Modal
          isOpen={Boolean(roleModalUser)}
          onClose={() => setRoleModalUser(null)}
          title="Confirm Role Modification"
        >
          <div className="space-y-4">
            <div className="p-3.5 bg-neutral-900 text-white rounded-xl text-xs space-y-2">
              <div className="flex items-center space-x-2 text-amber-400 font-bold uppercase tracking-wider text-[11px]">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>Stateful Session Invalidation Warning</span>
              </div>
              <p className="text-neutral-300 leading-relaxed">
                Modifying this account's authorization tier will immediately increment its session token version. Any existing active access tokens held by this user will be invalidated immediately.
              </p>
            </div>

            <div className="p-4 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl text-xs space-y-2 font-mono">
              <div className="flex justify-between">
                <span className="text-neutral-500">Target Identity:</span>
                <span className="font-semibold text-neutral-900">{roleModalUser.email}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-neutral-500">Current Role:</span>
                <span className="font-bold text-neutral-900">{roleModalUser.role}</span>
              </div>
              <div className="flex justify-between items-center pt-2 border-t border-[#E5E5E5]">
                <span className="text-neutral-500">Assigned Role:</span>
                <select
                  value={targetRole}
                  onChange={(e) => setTargetRole(e.target.value)}
                  className="bg-white border border-[#D4D4D4] rounded px-2.5 py-1 text-xs font-bold text-neutral-900 cursor-pointer"
                >
                  <option value="USER">USER (Standard)</option>
                  <option value="ADMIN">ADMIN (Operational)</option>
                </select>
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 pt-4 border-t border-[#E5E5E5]">
              <button
                type="button"
                onClick={() => setRoleModalUser(null)}
                disabled={roleUpdating}
                className="px-4 py-2 text-xs font-semibold text-neutral-700 bg-white border border-[#E5E5E5] rounded-lg hover:bg-neutral-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmRoleChange}
                disabled={roleUpdating}
                className="px-4 py-2 text-xs font-semibold text-white bg-neutral-900 rounded-lg hover:bg-neutral-800 disabled:opacity-50 cursor-pointer inline-flex items-center space-x-1.5"
              >
                {roleUpdating && <RotateCcw className="w-3.5 h-3.5 animate-spin" />}
                <span>Confirm Role Change</span>
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ========================================================================= */}
      {/* MODAL: ACCOUNT STATUS CHANGE CONFIRMATION */}
      {/* ========================================================================= */}
      {statusConfirmUser && (
        <Modal
          isOpen={Boolean(statusConfirmUser)}
          onClose={() => setStatusConfirmUser(null)}
          title={statusConfirmUser.is_active ? "Confirm Account Suspension" : "Confirm Account Reactivation"}
        >
          <div className="space-y-4">
            <p className="text-xs text-neutral-600 leading-relaxed">
              Are you sure you want to{" "}
              <strong className="text-neutral-900">
                {statusConfirmUser.is_active ? "suspend" : "reactivate"}
              </strong>{" "}
              the account for <span className="font-mono font-bold">{statusConfirmUser.email}</span>?
            </p>

            {statusConfirmUser.is_active && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700">
                Suspension revokes current active JWT tokens and blocks all protected requests with HTTP 403.
              </div>
            )}

            <div>
              <label className="block text-[11px] font-semibold text-neutral-700 uppercase tracking-wider mb-1 font-mono">
                Audit Log Reason (Optional)
              </label>
              <input
                type="text"
                value={statusReason}
                onChange={(e) => setStatusReason(e.target.value)}
                placeholder={statusConfirmUser.is_active ? "e.g., Security policy breach" : "e.g., Investigation completed"}
                className="w-full px-3 py-2 text-xs border border-[#E5E5E5] rounded-lg focus:outline-none focus:border-neutral-900"
              />
            </div>

            <div className="flex items-center justify-end space-x-3 pt-4 border-t border-[#E5E5E5]">
              <button
                type="button"
                onClick={() => setStatusConfirmUser(null)}
                disabled={statusUpdating}
                className="px-4 py-2 text-xs font-semibold text-neutral-700 bg-white border border-[#E5E5E5] rounded-lg hover:bg-neutral-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmStatusChange}
                disabled={statusUpdating}
                className={`px-4 py-2 text-xs font-semibold text-white rounded-lg disabled:opacity-50 cursor-pointer inline-flex items-center space-x-1.5 ${
                  statusConfirmUser.is_active ? "bg-red-600 hover:bg-red-700" : "bg-emerald-600 hover:bg-emerald-700"
                }`}
              >
                {statusUpdating && <RotateCcw className="w-3.5 h-3.5 animate-spin" />}
                <span>
                  {statusConfirmUser.is_active ? "Confirm Suspension" : "Confirm Reactivation"}
                </span>
              </button>
            </div>
          </div>
        </Modal>
      )}

      {/* ========================================================================= */}
      {/* MODAL: USER DETAILS INSPECTION */}
      {/* ========================================================================= */}
      {selectedUser && (
        <Modal
          isOpen={detailsModalOpen}
          onClose={() => {
            setDetailsModalOpen(false);
            setSelectedUser(null);
          }}
          title="Account Details"
        >
          <div className="space-y-4">
            <div className="flex items-center space-x-3.5 p-3.5 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl">
              <div className="w-12 h-12 rounded-full bg-neutral-900 text-white flex items-center justify-center font-bold text-sm shrink-0">
                {selectedUser.avatar || selectedUser.email.substring(0, 2).toUpperCase()}
              </div>
              <div className="min-w-0">
                <h4 className="font-semibold text-neutral-900 text-sm truncate">
                  {selectedUser.full_name || "Unnamed User"}
                </h4>
                <p className="text-xs text-neutral-500 font-mono truncate">
                  {selectedUser.email}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="p-3 bg-white border border-[#E5E5E5] rounded-lg">
                <span className="text-neutral-500 block text-[10px]">USER ID</span>
                <span className="font-bold text-neutral-900">#{selectedUser.id}</span>
              </div>

              <div className="p-3 bg-white border border-[#E5E5E5] rounded-lg">
                <span className="text-neutral-500 block text-[10px]">ROLE TIER</span>
                <span className="font-bold text-neutral-900">{selectedUser.role}</span>
              </div>

              <div className="p-3 bg-white border border-[#E5E5E5] rounded-lg">
                <span className="text-neutral-500 block text-[10px]">STATUS</span>
                <span className={`font-bold ${selectedUser.is_active ? "text-emerald-700" : "text-red-700"}`}>
                  {selectedUser.is_active ? "ACTIVE" : "SUSPENDED"}
                </span>
              </div>

              <div className="p-3 bg-white border border-[#E5E5E5] rounded-lg">
                <span className="text-neutral-500 block text-[10px]">REGISTERED</span>
                <span className="font-bold text-neutral-900">
                  {new Date(selectedUser.created_at).toLocaleDateString()}
                </span>
              </div>
            </div>

            {selectedUser.title && (
              <div className="p-3 bg-white border border-[#E5E5E5] rounded-lg text-xs font-mono">
                <span className="text-neutral-500 block text-[10px]">JOB POSITION / TITLE</span>
                <span className="font-semibold text-neutral-800">{selectedUser.title}</span>
              </div>
            )}
          </div>
        </Modal>
      )}

      {/* ========================================================================= */}
      {/* MODAL: AUDIT RECORD DETAIL INSPECTION */}
      {/* ========================================================================= */}
      {selectedAuditLog && (
        <Modal
          isOpen={Boolean(selectedAuditLog)}
          onClose={() => setSelectedAuditLog(null)}
          title={`Audit Record #${selectedAuditLog.id}`}
        >
          <div className="space-y-4 text-xs font-mono">
            <div className="grid grid-cols-2 gap-2 p-3 bg-[#F7F7F7] border border-[#E5E5E5] rounded-xl">
              <div>
                <span className="text-neutral-500 block text-[10px]">ACTION</span>
                <span className="font-bold text-neutral-900">{selectedAuditLog.action}</span>
              </div>
              <div>
                <span className="text-neutral-500 block text-[10px]">OUTCOME</span>
                <span className={`font-bold ${selectedAuditLog.status === "FAILURE" ? "text-red-700" : "text-emerald-700"}`}>
                  {selectedAuditLog.status}
                </span>
              </div>
              <div>
                <span className="text-neutral-500 block text-[10px]">ACTOR</span>
                <span className="text-neutral-800 truncate block">
                  {selectedAuditLog.actor_email || `#${selectedAuditLog.actor_id}` || "SYSTEM"}
                </span>
              </div>
              <div>
                <span className="text-neutral-500 block text-[10px]">TIMESTAMP (UTC)</span>
                <span className="text-neutral-800">
                  {new Date(selectedAuditLog.created_at).toISOString()}
                </span>
              </div>
            </div>

            <div>
              <span className="text-neutral-600 block text-[11px] font-bold mb-1 font-sans">
                Non-Sensitive Event Payload:
              </span>
              <pre className="p-3 bg-neutral-950 text-neutral-200 rounded-xl overflow-x-auto text-[11px] leading-relaxed max-h-48 border border-neutral-800">
                {selectedAuditLog.details || "No additional parameters recorded"}
              </pre>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
