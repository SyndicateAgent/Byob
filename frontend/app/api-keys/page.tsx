"use client";

import { FormEvent, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { apiRequest, setApiKey } from "@/lib/api";
import type { ApiKeyItem } from "@/lib/types";

interface ApiKeyCreateResponse extends ApiKeyItem {
  api_key: string;
}

export default function ApiKeysPage() {
  const [items, setItems] = useState<ApiKeyItem[]>([]);
  const [name, setName] = useState("");
  const [rateLimit, setRateLimit] = useState(600);
  const [createdKey, setCreatedKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const response = await apiRequest<{ data: ApiKeyItem[] }>("/api/v1/auth/api-keys");
    setItems(response.data);
  }

  useEffect(() => {
    load().catch((err: unknown) => setError(err instanceof Error ? err.message : "Load failed"));
  }, []);

  async function createKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const response = await apiRequest<ApiKeyCreateResponse>("/api/v1/auth/api-keys", {
      method: "POST",
      body: JSON.stringify({ name, rate_limit: rateLimit }),
    });
    setCreatedKey(response.api_key);
    setApiKey(response.api_key);
    setName("");
    await load();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">API Keys</h1>
        <p className="text-slate-500">Create keys for retrieval APIs and save one for console testing.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Create API Key</CardTitle>
          <CardDescription>The full key is only shown once and is cached locally for retrieval tests.</CardDescription>
        </CardHeader>
        <form className="flex gap-3" onSubmit={createKey}>
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="Name" required />
          <Input
            type="number"
            value={rateLimit}
            onChange={(event) => setRateLimit(Number(event.target.value))}
            min={1}
          />
          <Button type="submit">Create</Button>
        </form>
        {createdKey && (
          <p className="mt-4 rounded bg-blue-50 p-3 font-mono text-sm text-blue-800">{createdKey}</p>
        )}
      </Card>
      {error && <p className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      <div className="grid gap-4">
        {items.map((item) => (
          <Card key={item.id}>
            <div className="flex items-center justify-between">
              <div>
                <h2 className="font-semibold">{item.name}</h2>
                <p className="font-mono text-sm text-slate-500">{item.key_prefix ?? "hidden"}</p>
              </div>
              <div className="text-right text-sm">
                <p>{item.rate_limit} rpm</p>
                <p className={item.revoked ? "text-red-600" : "text-green-600"}>
                  {item.revoked ? "revoked" : "active"}
                </p>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
