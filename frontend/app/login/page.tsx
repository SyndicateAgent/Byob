"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest, setToken } from "@/lib/api";

interface TokenResponse {
  access_token: string;
}

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    try {
      const response = await apiRequest<TokenResponse>("/api/v1/auth/login", {
        method: "POST",
        auth: "none",
        body: JSON.stringify({ email, password }),
      });
      setToken(response.access_token);
      router.push("/knowledge-bases");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign in to BYOB</CardTitle>
          <CardDescription>Use a management console account.</CardDescription>
        </CardHeader>
        <form className="space-y-4" onSubmit={onSubmit}>
          <Input
            type="email"
            placeholder="admin@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
          <Input
            type="password"
            placeholder="Password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
          <Button className="w-full" type="submit">
            Sign in
          </Button>
        </form>
      </Card>
    </div>
  );
}
