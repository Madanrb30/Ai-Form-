import { describe, it, expect, vi, beforeEach } from "vitest";
import { api } from "../services/api";

describe("Admin API Service Unit Tests", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("calls getAdminStats successfully and returns aggregated metrics", async () => {
    const mockStats = {
      total_users: 15,
      active_users: 14,
      suspended_users: 1,
      users_by_role: { USER: 10, ADMIN: 4, SUPER_ADMIN: 1 },
      total_audit_logs: 45,
      total_forms: 8,
      total_submissions: 32,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => mockStats,
    });

    const stats = await api.getAdminStats();
    expect(stats.total_users).toBe(15);
    expect(stats.active_users).toBe(14);
    expect(stats.users_by_role.ADMIN).toBe(4);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining("/admin/stats"),
      expect.any(Object)
    );
  });

  it("calls getAdminUsers with search, role, status, and pagination query params", async () => {
    const mockUsers = {
      items: [
        {
          id: 1,
          email: "admin@example.com",
          full_name: "Admin User",
          role: "ADMIN",
          is_active: true,
          created_at: "2026-10-14T10:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
      total_pages: 1,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => mockUsers,
    });

    const result = await api.getAdminUsers({
      search: "admin",
      role: "ADMIN",
      status: "active",
      page: 1,
      limit: 10,
    });

    expect(result.items.length).toBe(1);
    expect(result.items[0].email).toBe("admin@example.com");

    const fetchCall = global.fetch.mock.calls[0];
    const requestedUrl = fetchCall[0];
    expect(requestedUrl).toContain("/admin/users");
    expect(requestedUrl).toContain("search=admin");
    expect(requestedUrl).toContain("role=ADMIN");
    expect(requestedUrl).toContain("status=active");
    expect(requestedUrl).toContain("page=1");
    expect(requestedUrl).toContain("limit=10");
  });

  it("calls updateAdminUserStatus and handles 403 forbidden responses appropriately", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      statusText: "Forbidden",
      headers: { get: () => "application/json" },
      json: async () => ({
        detail: "Admins cannot modify another Admin or Super Admin account status.",
      }),
    });

    await expect(api.updateAdminUserStatus(2, false)).rejects.toThrow(
      "Admins cannot modify another Admin or Super Admin account status."
    );
  });

  it("calls getAdminAuditLogs with action and pagination parameters", async () => {
    const mockLogs = {
      items: [
        {
          id: 10,
          actor_id: 1,
          actor_email: "admin@example.com",
          actor_role: "ADMIN",
          action: "USER_SUSPENDED",
          target_type: "User",
          target_id: 2,
          outcome: "SUCCESS",
          details: "Account suspended by admin",
          timestamp: "2026-10-14T12:00:00Z",
        },
      ],
      total: 1,
      page: 1,
      page_size: 15,
      total_pages: 1,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: { get: () => "application/json" },
      json: async () => mockLogs,
    });

    const logs = await api.getAdminAuditLogs({
      action: "USER_SUSPENDED",
      page: 1,
      pageSize: 15,
    });

    expect(logs.items.length).toBe(1);
    expect(logs.items[0].action).toBe("USER_SUSPENDED");
    expect(logs.items[0].outcome).toBe("SUCCESS");

    const requestedUrl = global.fetch.mock.calls[0][0];
    expect(requestedUrl).toContain("/admin/audit-logs");
    expect(requestedUrl).toContain("action=USER_SUSPENDED");
  });
});
