"use client";

import { FormEvent, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { Label, Select } from "@/components/ui/select";
import { Table, TBody, TD, TH, THead, TR } from "@/components/ui/table";
import { apiRequest, getCurrentUserFromToken } from "@/lib/api";
import { formatDate } from "@/lib/utils";
import type { UserItem } from "@/lib/types";

export default function UsersPage() {
  const [items, setItems] = useState<UserItem[]>([]);
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("viewer");
  const [error, setError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [editing, setEditing] = useState<UserItem | null>(null);
  const [editRole, setEditRole] = useState("viewer");
  const [editPassword, setEditPassword] = useState("");

  const currentUser = typeof window !== "undefined" ? getCurrentUserFromToken() : null;

  async function load() {
    const response = await apiRequest<{ data: UserItem[] }>("/api/v1/users");
    setItems(response.data);
  }

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreateError(null);
    try {
      await apiRequest("/api/v1/users", {
        method: "POST",
        body: JSON.stringify({ email, password, role }),
      });
      setOpen(false);
      setEmail("");
      setPassword("");
      setRole("viewer");
      await load();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Create failed");
    }
  }

  function openEdit(user: UserItem) {
    setEditing(user);
    setEditRole(user.role);
    setEditPassword("");
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing) return;
    const body: Record<string, string> = {};
    if (editRole !== editing.role) body.role = editRole;
    if (editPassword) body.password = editPassword;
    if (Object.keys(body).length === 0) {
      setEditing(null);
      return;
    }
    try {
      await apiRequest(`/api/v1/users/${editing.id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setEditing(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  async function removeUser(user: UserItem) {
    if (!window.confirm(`Delete user ${user.email}?`)) return;
    try {
      await apiRequest(`/api/v1/users/${user.id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="space-y-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Users</h1>
          <p className="text-sm text-slate-500">Manage local management console accounts.</p>
        </div>
        <Button className="gap-2" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" /> New user
        </Button>
      </header>
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <Card className="p-0">
        <Table>
          <THead>
            <TR>
              <TH>Email</TH>
              <TH>Role</TH>
              <TH>Created</TH>
              <TH className="text-right">Actions</TH>
            </TR>
          </THead>
          <TBody>
            {items.map((item) => {
              const isSelf = currentUser?.sub === item.id;
              return (
                <TR key={item.id}>
                  <TD className="font-medium">{item.email}</TD>
                  <TD>
                    <Badge variant={item.role === "admin" ? "info" : "muted"}>{item.role}</Badge>
                    {isSelf && <span className="ml-2 text-xs text-slate-400">you</span>}
                  </TD>
                  <TD>{formatDate(item.created_at)}</TD>
                  <TD className="text-right">
                    <div className="inline-flex gap-2">
                      <Button variant="outline" onClick={() => openEdit(item)}>
                        Edit
                      </Button>
                      <Button
                        variant="destructive"
                        onClick={() => removeUser(item)}
                        disabled={isSelf}
                        title={isSelf ? "You cannot delete your own account" : "Delete user"}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TD>
                </TR>
              );
            })}
            {items.length === 0 && (
              <TR>
                <TD colSpan={4} className="text-center text-sm text-slate-500">
                  No users yet.
                </TD>
              </TR>
            )}
          </TBody>
        </Table>
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Create user"
        description="The new user can sign in with the email and password provided."
      >
        <form className="space-y-4" onSubmit={createUser}>
          <div className="space-y-1">
            <Label htmlFor="new-user-email">Email</Label>
            <Input
              id="new-user-email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="new-user-password">Password</Label>
            <Input
              id="new-user-password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              minLength={12}
              required
            />
            <p className="text-xs text-slate-500">Minimum 12 characters.</p>
          </div>
          <div className="space-y-1">
            <Label htmlFor="new-user-role">Role</Label>
            <Select id="new-user-role" value={role} onChange={(event) => setRole(event.target.value)}>
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
              <option value="admin">Admin</option>
            </Select>
          </div>
          {createError && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{createError}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit">Create</Button>
          </div>
        </form>
      </Modal>

      <Modal open={editing !== null} onClose={() => setEditing(null)} title={`Edit ${editing?.email ?? ""}`}>
        <form className="space-y-4" onSubmit={saveEdit}>
          <div className="space-y-1">
            <Label htmlFor="edit-user-role">Role</Label>
            <Select id="edit-user-role" value={editRole} onChange={(event) => setEditRole(event.target.value)}>
              <option value="viewer">Viewer</option>
              <option value="editor">Editor</option>
              <option value="admin">Admin</option>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="edit-user-password">New password (optional)</Label>
            <Input
              id="edit-user-password"
              type="password"
              value={editPassword}
              onChange={(event) => setEditPassword(event.target.value)}
              minLength={12}
              placeholder="Leave blank to keep current password"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button type="submit">Save</Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
