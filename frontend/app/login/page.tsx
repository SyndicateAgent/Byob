"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/select";
import { apiRequest, setToken } from "@/lib/api";

interface TokenResponse {
  access_token: string;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const response = await apiRequest<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        auth: "none",
        body: JSON.stringify({ email, password }),
      });
      setToken(response.access_token);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-slate-950 p-6 text-slate-100">
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(90deg,_rgba(148,163,184,.12)_1px,_transparent_1px),linear-gradient(0deg,_rgba(148,163,184,.10)_1px,_transparent_1px)] bg-[size:32px_32px]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300/70 to-transparent" />
      <div className="relative grid w-full max-w-5xl gap-10 lg:grid-cols-[1.1fr_1fr]">
        <div className="hidden animate-fade-up flex-col justify-between text-slate-200 lg:flex">
          <div>
            <p className="text-xs uppercase text-slate-400">BYOB Console</p>
            <h1 className="mt-4 text-4xl font-semibold leading-tight text-white">
              BYOB Vector Database
            </h1>
            <p className="mt-3 max-w-md text-sm text-slate-300">
              A self-hosted vector database management system for AI Agents, with managed ingestion,
              Qdrant-backed hybrid search, and local retrieval APIs.
            </p>
          </div>
          <ul className="space-y-3 text-sm text-slate-300">
            <li>Hybrid retrieval with rerank</li>
            <li>Knowledge base and document management</li>
            <li>Direct local API access for AI Agents</li>
          </ul>
        </div>
        <Card className="animate-soft-pop w-full bg-white text-slate-900 shadow-2xl">
          <CardHeader>
            <CardTitle>Sign in to BYOB</CardTitle>
            <CardDescription>Use a local management console account.</CardDescription>
          </CardHeader>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-1">
              <Label htmlFor="login-email">Email</Label>
              <Input
                id="login-email"
                type="email"
                placeholder="admin@example.com"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="login-password">Password</Label>
              <Input
                id="login-password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </div>
            {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
            <Button className="w-full" type="submit" disabled={submitting}>
              {submitting ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
