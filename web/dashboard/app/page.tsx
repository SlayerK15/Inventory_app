"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

interface InventoryItem {
  id: number;
  sku: string;
  name: string;
  description?: string | null;
  quantity: number;
  location?: string | null;
  reorder_point: number;
  tenant_id: string;
  created_at: string;
  updated_at: string;
}

interface DashboardSummary {
  user: {
    id: number;
    email: string;
    full_name: string;
    role: string;
    tenant_id: string;
    created_at: string;
  };
  inventory: InventoryItem[];
  low_stock: InventoryItem[];
}

interface LoginResponse {
  access_token: string;
  token_type: string;
}

const gatewayUrl = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "http://localhost:8080";

export default function Dashboard() {
  const [token, setToken] = useState<string | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [adjusting, setAdjusting] = useState(false);

  const isAuthenticated = useMemo(() => Boolean(token), [token]);

  const loadDashboard = useCallback(async () => {
    if (!token) {
      setSummary(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${gatewayUrl}/dashboard`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!response.ok) {
        throw new Error(`Gateway responded with ${response.status}`);
      }
      const payload = (await response.json()) as DashboardSummary;
      setSummary(payload);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    const stored = window.localStorage.getItem("inventory_token");
    if (stored) {
      setToken(stored);
    }
  }, []);

  useEffect(() => {
    if (token) {
      window.localStorage.setItem("inventory_token", token);
      loadDashboard().catch((err) => setError((err as Error).message));
    } else {
      window.localStorage.removeItem("inventory_token");
    }
  }, [token, loadDashboard]);

  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const payload = {
      email: form.get("email"),
      password: form.get("password"),
    };

    try {
      setError(null);
      const response = await fetch(`${gatewayUrl}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Login failed with status ${response.status}`);
      }
      const auth = (await response.json()) as LoginResponse;
      setToken(auth.access_token);
      event.currentTarget.reset();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setSummary(null);
  };

  const handleCreate = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    const form = new FormData(event.currentTarget);
    const payload = {
      sku: form.get("sku"),
      name: form.get("name"),
      description: form.get("description") || null,
      quantity: Number(form.get("quantity") ?? 0),
      reorder_point: Number(form.get("reorder_point") ?? 0),
      location: form.get("location") || null,
      tenant_id: form.get("tenant_id") || "default-tenant",
    };

    try {
      setCreating(true);
      const response = await fetch(`${gatewayUrl}/inventory`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Create failed with status ${response.status}`);
      }
      event.currentTarget.reset();
      await loadDashboard();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCreating(false);
    }
  };

  const handleAdjust = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) return;
    const form = new FormData(event.currentTarget);
    const itemId = form.get("item_id");
    if (!itemId) return;
    const payload = {
      delta: Number(form.get("delta") ?? 0),
      reason: form.get("reason") || null,
    };

    try {
      setAdjusting(true);
      const response = await fetch(`${gatewayUrl}/inventory/${itemId}/adjust`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `Adjust failed with status ${response.status}`);
      }
      event.currentTarget.reset();
      await loadDashboard();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setAdjusting(false);
    }
  };

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold">Inventory Operations</h1>
          <p className="text-slate-400 mt-2">
            Use the gateway-backed dashboard to authenticate, inspect, and manage
            stock across the platform.
          </p>
        </div>
        {isAuthenticated ? (
          <button
            onClick={handleLogout}
            className="rounded bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-400"
          >
            Sign out
          </button>
        ) : null}
      </header>

      {error ? (
        <div className="rounded-md border border-red-500/40 bg-red-500/10 p-4 text-red-200">
          <strong className="block">Something went wrong</strong>
          <span>{error}</span>
        </div>
      ) : null}

      {!isAuthenticated ? (
        <section className="max-w-md space-y-4 rounded-md border border-slate-700 bg-slate-900 p-6">
          <header>
            <h2 className="text-lg font-semibold">Sign in</h2>
            <p className="text-sm text-slate-400">
              Use the credentials created through the account service to obtain an
              access token.
            </p>
          </header>
          <form onSubmit={handleLogin} className="space-y-4">
            <label className="block space-y-1">
              <span className="text-xs uppercase tracking-wide text-slate-400">Email</span>
              <input
                name="email"
                type="email"
                required
                className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2"
              />
            </label>
            <label className="block space-y-1">
              <span className="text-xs uppercase tracking-wide text-slate-400">Password</span>
              <input
                name="password"
                type="password"
                required
                className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2"
              />
            </label>
            <button
              type="submit"
              className="w-full rounded bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400"
            >
              Sign in
            </button>
          </form>
        </section>
      ) : (
        <>
          <section className="grid gap-6 md:grid-cols-2">
            <div className="rounded-md border border-slate-700 bg-slate-900 p-6">
              <h2 className="text-lg font-medium">Account</h2>
              {summary ? (
                <dl className="mt-4 grid gap-2">
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-400">Email</dt>
                    <dd className="text-base">{summary.user.email}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-400">Role</dt>
                    <dd className="text-base">{summary.user.role}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-slate-400">Tenant</dt>
                    <dd className="text-base">{summary.user.tenant_id}</dd>
                  </div>
                </dl>
              ) : (
                <p className="text-sm text-slate-400">Loading profile…</p>
              )}
            </div>

            <div className="rounded-md border border-slate-700 bg-slate-900 p-6">
              <h2 className="text-lg font-medium">Create item</h2>
              <form onSubmit={handleCreate} className="mt-4 space-y-3">
                <div className="grid gap-3 md:grid-cols-2">
                  <label className="space-y-1 text-sm">
                    <span className="text-xs uppercase tracking-wide text-slate-400">SKU</span>
                    <input name="sku" required className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                  </label>
                  <label className="space-y-1 text-sm">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Name</span>
                    <input name="name" required className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                  </label>
                  <label className="space-y-1 text-sm">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Quantity</span>
                    <input name="quantity" type="number" min={0} defaultValue={0} className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                  </label>
                  <label className="space-y-1 text-sm">
                    <span className="text-xs uppercase tracking-wide text-slate-400">Reorder point</span>
                    <input name="reorder_point" type="number" min={0} defaultValue={0} className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                  </label>
                </div>
                <label className="space-y-1 text-sm">
                  <span className="text-xs uppercase tracking-wide text-slate-400">Location</span>
                  <input name="location" className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-xs uppercase tracking-wide text-slate-400">Description</span>
                  <textarea name="description" rows={3} className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-xs uppercase tracking-wide text-slate-400">Tenant</span>
                  <input name="tenant_id" defaultValue="default-tenant" className="w-full rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                </label>
                <button
                  type="submit"
                  disabled={creating}
                  className="w-full rounded bg-emerald-500 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-400 disabled:opacity-60"
                >
                  {creating ? "Creating…" : "Create item"}
                </button>
              </form>
            </div>
          </section>

          <section className="rounded-md border border-slate-700 bg-slate-900 p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-medium">Inventory</h2>
              <form onSubmit={handleAdjust} className="flex flex-wrap items-end gap-3">
                <label className="space-y-1 text-sm">
                  <span className="text-xs uppercase tracking-wide text-slate-400">Item ID</span>
                  <input name="item_id" required className="w-32 rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-xs uppercase tracking-wide text-slate-400">Quantity change</span>
                  <input name="delta" type="number" required className="w-32 rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-xs uppercase tracking-wide text-slate-400">Reason</span>
                  <input name="reason" className="w-48 rounded border border-slate-700 bg-slate-950 px-3 py-2" />
                </label>
                <button
                  type="submit"
                  disabled={adjusting}
                  className="rounded bg-sky-500 px-4 py-2 text-sm font-medium text-white hover:bg-sky-400 disabled:opacity-60"
                >
                  {adjusting ? "Saving…" : "Adjust"}
                </button>
              </form>
            </div>

            <div className="mt-6 overflow-x-auto">
              {loading ? (
                <p className="text-sm text-slate-400">Loading inventory…</p>
              ) : summary && summary.inventory.length > 0 ? (
                <table className="min-w-full divide-y divide-slate-800 text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase tracking-wide text-slate-400">
                      <th className="px-3 py-2">ID</th>
                      <th className="px-3 py-2">SKU</th>
                      <th className="px-3 py-2">Item</th>
                      <th className="px-3 py-2">Quantity</th>
                      <th className="px-3 py-2">Reorder point</th>
                      <th className="px-3 py-2">Location</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {summary.inventory.map((item) => (
                      <tr key={item.id}>
                        <td className="px-3 py-2 text-slate-200">{item.id}</td>
                        <td className="px-3 py-2 text-slate-200">{item.sku}</td>
                        <td className="px-3 py-2 text-slate-200">{item.name}</td>
                        <td className="px-3 py-2 text-slate-200">{item.quantity}</td>
                        <td className="px-3 py-2 text-slate-200">{item.reorder_point}</td>
                        <td className="px-3 py-2 text-slate-200">{item.location ?? "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="text-sm text-slate-400">No items found yet. Create your first item above.</p>
              )}
            </div>

            {summary && summary.low_stock.length > 0 ? (
              <div className="mt-6 rounded border border-amber-500/40 bg-amber-500/10 p-4 text-amber-200">
                <strong className="block">Low stock alerts</strong>
                <ul className="mt-2 space-y-1 text-sm">
                  {summary.low_stock.map((item) => (
                    <li key={`low-${item.id}`}>
                      {item.name} ({item.sku}) is down to {item.quantity} units.
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </section>
        </>
      )}
    </div>
  );
}
