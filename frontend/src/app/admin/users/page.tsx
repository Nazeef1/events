"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

export default function AdminUsersPage() {
  const [users, setUsers] = useState<User[] | null>(null);

  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<User[]>("/users").then(setUsers).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="mx-auto max-w-4xl px-6 py-12">
      <h1 className="font-display text-3xl mb-8">Users</h1>
      {error && <p className="text-rust text-sm mb-4">{error}</p>}
      <table className="w-full text-sm hairline border-collapse">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wide text-muted border-b border-line">
            <th className="p-3">Name</th>
            <th className="p-3">Email</th>
            <th className="p-3">Role</th>
            <th className="p-3">Joined</th>
          </tr>
        </thead>
        <tbody>
          {users?.map((u) => (
            <tr key={u.id} className="border-b border-line last:border-0">
              <td className="p-3">{u.full_name}</td>
              <td className="p-3 text-muted">{u.email}</td>
              <td className="p-3 text-xs uppercase tracking-wide">{u.role}</td>
              <td className="p-3 text-muted">{new Date(u.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
