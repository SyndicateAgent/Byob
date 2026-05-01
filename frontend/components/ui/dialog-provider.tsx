"use client";

import * as React from "react";
import { CircleAlert, Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";

type ConfirmVariant = "default" | "destructive";
type AlertVariant = "default" | "destructive" | "info";

interface ConfirmOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: ConfirmVariant;
}

interface AlertOptions {
  title: string;
  description?: string;
  confirmLabel?: string;
  variant?: AlertVariant;
}

type QueuedDialog =
  | {
      id: number;
      kind: "confirm";
      options: ConfirmOptions;
      resolve: (value: boolean) => void;
    }
  | {
      id: number;
      kind: "alert";
      options: AlertOptions;
      resolve: () => void;
    };

interface DialogContextValue {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  alert: (options: AlertOptions) => Promise<void>;
}

const DialogContext = React.createContext<DialogContextValue | null>(null);

const confirmToneClasses: Record<ConfirmVariant, string> = {
  default: "border-blue-100 bg-blue-50 text-blue-700",
  destructive: "border-red-100 bg-red-50 text-red-700",
};

const alertToneClasses: Record<AlertVariant, string> = {
  default: "border-blue-100 bg-blue-50 text-blue-700",
  destructive: "border-red-100 bg-red-50 text-red-700",
  info: "border-cyan-100 bg-cyan-50 text-cyan-700",
};

export function DialogProvider({ children }: { children: React.ReactNode }) {
  const [queue, setQueue] = React.useState<QueuedDialog[]>([]);
  const nextIdRef = React.useRef(1);
  const current = queue[0] ?? null;

  const shiftQueue = React.useCallback(() => {
    setQueue((existing) => existing.slice(1));
  }, []);

  const confirm = React.useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setQueue((existing) => [
        ...existing,
        { id: nextIdRef.current++, kind: "confirm", options, resolve },
      ]);
    });
  }, []);

  const alert = React.useCallback((options: AlertOptions) => {
    return new Promise<void>((resolve) => {
      setQueue((existing) => [
        ...existing,
        { id: nextIdRef.current++, kind: "alert", options, resolve },
      ]);
    });
  }, []);

  const contextValue = React.useMemo<DialogContextValue>(
    () => ({ confirm, alert }),
    [alert, confirm],
  );

  function closeCurrent(result?: boolean) {
    if (!current) return;

    if (current.kind === "confirm") {
      current.resolve(result ?? false);
    } else {
      current.resolve();
    }

    shiftQueue();
  }

  const dialogVariant = current?.options.variant ?? "default";

  return (
    <DialogContext.Provider value={contextValue}>
      {children}
      {current && (
        <Modal
          open
          onClose={() => closeCurrent(false)}
          title={current.options.title}
          description={current.options.description}
          className="max-w-md"
        >
          <div className="space-y-5">
            <div className="flex items-start gap-3">
              <div
                className={
                  current.kind === "confirm"
                    ? `flex h-10 w-10 items-center justify-center rounded-xl border ${confirmToneClasses[dialogVariant as ConfirmVariant]}`
                    : `flex h-10 w-10 items-center justify-center rounded-xl border ${alertToneClasses[dialogVariant as AlertVariant]}`
                }
              >
                {current.kind === "confirm" ? (
                  <CircleAlert className="h-5 w-5" />
                ) : (
                  <Info className="h-5 w-5" />
                )}
              </div>
              <p className="pt-1 text-sm leading-6 text-slate-600">
                {current.kind === "confirm"
                  ? "Please confirm this action before continuing."
                  : "Review the message and continue when you are ready."}
              </p>
            </div>
            <div className="flex justify-end gap-2">
              {current.kind === "confirm" && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => closeCurrent(false)}
                >
                  {current.options.cancelLabel ?? "Cancel"}
                </Button>
              )}
              <Button
                type="button"
                variant={dialogVariant === "destructive" ? "destructive" : "default"}
                onClick={() => closeCurrent(true)}
              >
                {current.options.confirmLabel ?? (current.kind === "confirm" ? "Confirm" : "OK")}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </DialogContext.Provider>
  );
}

export function useDialog() {
  const context = React.useContext(DialogContext);
  if (!context) {
    throw new Error("useDialog must be used within a DialogProvider");
  }
  return context;
}