"use client";

import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface ParsedOption {
  label: string;
  value: string;
  disabled: boolean;
}

function getNodeText(node: React.ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(getNodeText).join("");
  if (React.isValidElement<{ children?: React.ReactNode }>(node)) return getNodeText(node.props.children);
  return "";
}

function parseOptions(children: React.ReactNode): ParsedOption[] {
  return React.Children.toArray(children).flatMap((child) => {
    if (!React.isValidElement<{ value?: string | number; disabled?: boolean; children?: React.ReactNode }>(child)) {
      return [];
    }

    if (child.type !== "option") return [];

    return [
      {
        label: getNodeText(child.props.children),
        value: String(child.props.value ?? ""),
        disabled: Boolean(child.props.disabled),
      },
    ];
  });
}

export function Select({ className, children, value, defaultValue, onChange, disabled, name, id }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const rootRef = React.useRef<HTMLDivElement | null>(null);
  const triggerRef = React.useRef<HTMLButtonElement | null>(null);
  const options = React.useMemo(() => parseOptions(children), [children]);
  const [open, setOpen] = React.useState(false);
  const [internalValue, setInternalValue] = React.useState(String(defaultValue ?? options[0]?.value ?? ""));

  const selectedValue = value !== undefined ? String(value) : internalValue;
  const selectedOption = options.find((option) => option.value === selectedValue) ?? options[0];

  React.useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        triggerRef.current?.focus();
      }
    };

    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  function commitValue(nextValue: string) {
    if (value === undefined) {
      setInternalValue(nextValue);
    }

    const syntheticEvent = {
      target: { value: nextValue, name, id } as EventTarget & HTMLSelectElement,
      currentTarget: { value: nextValue, name, id } as EventTarget & HTMLSelectElement,
    } as React.ChangeEvent<HTMLSelectElement>;

    onChange?.(syntheticEvent);
    setOpen(false);
    triggerRef.current?.focus();
  }

  function moveSelection(direction: 1 | -1) {
    const enabledOptions = options.filter((option) => !option.disabled);
    if (enabledOptions.length === 0) return;

    const currentIndex = Math.max(
      enabledOptions.findIndex((option) => option.value === selectedValue),
      0,
    );
    const nextIndex = (currentIndex + direction + enabledOptions.length) % enabledOptions.length;
    commitValue(enabledOptions[nextIndex].value);
  }

  return (
    <div ref={rootRef} className="relative">
      {name && <input type="hidden" name={name} value={selectedValue} />}
      <button
        ref={triggerRef}
        id={id}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        className={cn(
          "group flex h-10 w-full items-center justify-between gap-3 rounded-md border border-slate-300 bg-[linear-gradient(180deg,rgba(255,255,255,0.98)_0%,rgba(248,250,252,0.98)_100%)] px-3 text-left text-sm text-slate-900 shadow-[inset_0_1px_0_rgba(255,255,255,0.65)] outline-none transition-all duration-200 hover:border-slate-400 hover:bg-white focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:cursor-not-allowed disabled:border-slate-200 disabled:bg-slate-100 disabled:text-slate-400",
          className,
        )}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (disabled) return;
          if (event.key === "ArrowDown") {
            event.preventDefault();
            if (!open) {
              setOpen(true);
              return;
            }
            moveSelection(1);
          }
          if (event.key === "ArrowUp") {
            event.preventDefault();
            if (!open) {
              setOpen(true);
              return;
            }
            moveSelection(-1);
          }
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setOpen((current) => !current);
          }
        }}
      >
        <span className="min-w-0 truncate">{selectedOption?.label ?? "Select an option"}</span>
        <span className="flex items-center gap-3">
          <span className="h-5 w-px rounded-full bg-slate-200 transition-colors duration-200 group-focus-within:bg-blue-200 group-data-[open=true]:bg-blue-200" />
          <ChevronDown className={cn("h-4 w-4 text-slate-400 transition-all duration-200 group-hover:text-slate-500 group-focus:text-blue-600", open && "rotate-180 text-blue-600")} />
        </span>
      </button>
      {open && options.length > 0 && (
        <div className="animate-soft-pop absolute left-0 right-0 top-[calc(100%+0.5rem)] z-30 overflow-hidden rounded-xl border border-slate-200 bg-white/95 shadow-[0_24px_60px_rgba(15,23,42,0.16)] backdrop-blur">
          <div className="border-b border-slate-100 bg-[linear-gradient(180deg,rgba(248,250,252,0.92)_0%,rgba(255,255,255,0.96)_100%)] px-3 py-2 text-[11px] font-medium uppercase text-slate-500">
            Select an option
          </div>
          <div className="max-h-64 overflow-y-auto p-2" role="listbox" aria-labelledby={id}>
            {options.map((option) => {
              const active = option.value === selectedValue;

              return (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={active}
                  disabled={option.disabled}
                  className={cn(
                    "flex w-full items-center justify-between gap-3 rounded-lg px-3 py-2.5 text-sm transition-all duration-200",
                    active && "bg-blue-50 text-blue-700 shadow-sm",
                    !active && "text-slate-700 hover:bg-slate-100 hover:text-slate-950",
                    option.disabled && "cursor-not-allowed opacity-45",
                  )}
                  onClick={() => !option.disabled && commitValue(option.value)}
                >
                  <span className="truncate">{option.label}</span>
                  <span
                    className={cn(
                      "flex h-5 w-5 items-center justify-center rounded-full border transition-all duration-200",
                      active ? "border-blue-200 bg-white text-blue-600" : "border-slate-200 bg-slate-50 text-transparent",
                    )}
                  >
                    <Check className="h-3.5 w-3.5" />
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label className={cn("text-xs font-medium uppercase text-slate-600", className)} {...props} />
  );
}
