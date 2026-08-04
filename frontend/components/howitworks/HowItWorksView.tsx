"use client";

import {
  Activity,
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Clock,
  Cog,
  EyeOff,
  LayoutDashboard,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { useGuideDismissed } from "@/lib/hooks/useGuideDismissed";

import { CoreFlowSimulator } from "./CoreFlowSimulator";

const STATS = [
  { icon: LayoutDashboard, label: "10 module types" },
  { icon: ShieldCheck, label: "Every write reviewed" },
  { icon: Clock, label: "7-day pending TTL" },
] as const;

const USAGES = [
  {
    icon: LayoutDashboard,
    title: "Pages & modules",
    body: "Build dashboards from 10 module types — markdown, key/value, tables, timeseries, log streams, links, action buttons and more. Each page is a grid you arrange in edit mode.",
  },
  {
    icon: CheckCircle2,
    title: "Approvals",
    body: "Every change an agent proposes that isn't auto-decided lands here. Review the preview, then approve or deny it.",
    href: "/approvals",
    cta: "Open approvals",
  },
  {
    icon: Activity,
    title: "Activity",
    body: "A complete audit log of every change — who did what, when, and the before/after. Searchable history of the whole system.",
    href: "/activity",
    cta: "Open activity",
  },
  {
    icon: Cog,
    title: "Agents & rules",
    body: "Register the MCP agents that may propose changes, and write approval rules that auto-approve or auto-deny future writes so you only get prompted for what matters.",
    href: "/settings/agents",
    cta: "Open settings",
  },
] as const;

const STEPS = [
  {
    title: "Register an agent",
    body: "In Settings → Agents, create an agent and copy its API key into your MCP client. That key is how the agent authenticates.",
  },
  {
    title: "Create a page & add modules",
    body: "Make a dashboard page and drop in modules. Agents can also propose new modules for you to approve.",
  },
  {
    title: "Approve the first change",
    body: "When an agent proposes a write, it appears in Approvals. Decide it once — then add a rule so similar writes decide themselves.",
  },
] as const;

export function HowItWorksView() {
  const { dismissed, dismiss, restore } = useGuideDismissed();

  return (
    <article className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[var(--border)] bg-[var(--muted)]/60 px-4 py-3">
        <p className="text-sm text-[var(--muted-fg)]">
          {dismissed ? (
            <>
              This guide is hidden from the sidebar. You can always reopen it from{" "}
              <span className="font-medium text-[var(--fg)]">Settings → Help</span>.
            </>
          ) : (
            <>
              This guide is pinned to your sidebar. Hide it when you&apos;re done — you can bring it
              back from <span className="font-medium text-[var(--fg)]">Settings → Help</span>.
            </>
          )}
        </p>
        <Button variant="secondary" size="sm" onClick={dismissed ? restore : dismiss}>
          {dismissed ? (
            "Show in sidebar"
          ) : (
            <>
              <EyeOff className="size-4" /> Hide from sidebar
            </>
          )}
        </Button>
      </div>

      {/* Hero */}
      <section className="relative overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--card)] px-5 py-8 shadow-[var(--shadow-sm)] sm:px-8 sm:py-10">
        <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
          <div
            className="absolute -top-28 left-1/2 h-72 w-[44rem] max-w-[130%] -translate-x-1/2 rounded-full blur-3xl"
            style={{
              background:
                "radial-gradient(closest-side, color-mix(in srgb, var(--accent) 20%, transparent), transparent)",
            }}
          />
        </div>
        <div className="relative flex flex-col gap-4">
          <Badge className="w-fit border-[var(--border)] bg-[var(--bg)] text-[var(--muted-fg)]">
            <ShieldCheck className="size-3.5 text-[var(--accent)]" /> Self-hosted · Tailscale-only
          </Badge>
          <div className="max-w-2xl">
            <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
              How pdash works
            </h1>
            <p className="mt-2 text-sm leading-relaxed text-[var(--muted-fg)] sm:text-base">
              Build dashboards from modules, let AI agents keep them current over MCP — and stay in
              control, because every agent write flows through an approval engine first.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {STATS.map((s) => {
              const Icon = s.icon;
              return (
                <span
                  key={s.label}
                  className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--bg)] px-3 py-1 text-xs font-medium text-[var(--muted-fg)]"
                >
                  <Icon className="size-3.5 text-[var(--accent)]" />
                  {s.label}
                </span>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            <Link
              href="/settings/agents"
              className="inline-flex h-9 items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-4 text-sm font-medium text-[var(--accent-fg)] shadow-[var(--shadow-xs)] outline-none transition-colors hover:bg-[var(--accent-hover)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
            >
              Register your first agent
              <ArrowRight className="size-4" />
            </Link>
            <a
              href="#hiw-flow"
              className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--card)] px-4 text-sm font-medium shadow-[var(--shadow-xs)] outline-none transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--muted)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
            >
              See the flow
            </a>
          </div>
        </div>
      </section>

      {/* What is pdash? */}
      <section aria-labelledby="hiw-what" className="flex flex-col gap-3">
        <h2 id="hiw-what" className="text-lg font-semibold tracking-tight">
          What is pdash?
        </h2>
        <Card>
          <CardBody>
            <p className="text-sm leading-relaxed text-[var(--fg)]">
              pdash is a self-hosted, single-admin command center for your homelab. You build
              dashboards out of <span className="font-medium">modules</span>, and AI agents connect
              over <span className="font-medium">MCP</span> to keep them up to date. The catch:
              agents never change anything directly — every write they make flows through an{" "}
              <span className="font-medium">approval engine</span> first, so you stay in control.
            </p>
          </CardBody>
        </Card>
      </section>

      {/* The core flow — interactive */}
      <section id="hiw-flow" aria-labelledby="hiw-flow-h" className="flex flex-col gap-3 scroll-mt-4">
        <div>
          <h2 id="hiw-flow-h" className="text-lg font-semibold tracking-tight">
            See how a change flows
          </h2>
          <p className="mt-0.5 text-sm text-[var(--muted-fg)]">
            Step through it — and switch the engine&apos;s verdict to watch the same change branch
            three ways.
          </p>
        </div>
        <CoreFlowSimulator />
      </section>

      {/* Core usages */}
      <section aria-labelledby="hiw-use" className="flex flex-col gap-3">
        <h2 id="hiw-use" className="text-lg font-semibold tracking-tight">
          What you&apos;ll use
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {USAGES.map((u) => {
            const Icon = u.icon;
            return (
              <div
                key={u.title}
                className="group flex gap-3 rounded-xl border border-[var(--border)] bg-[var(--card)] p-4 shadow-[var(--shadow-sm)] transition-all hover:border-[var(--border-strong)] hover:shadow-[var(--shadow-md)] motion-safe:hover:-translate-y-0.5"
              >
                <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-[var(--accent-soft)] text-[var(--accent)] transition-colors group-hover:bg-[var(--accent)] group-hover:text-[var(--accent-fg)]">
                  <Icon className="size-5" />
                </div>
                <div className="min-w-0">
                  <p className="font-medium">{u.title}</p>
                  <p className="mt-1 text-sm leading-relaxed text-[var(--muted-fg)]">{u.body}</p>
                  {"href" in u && u.href && (
                    <Link
                      href={u.href}
                      className="mt-2 inline-flex items-center gap-0.5 rounded-sm text-sm font-medium text-[var(--accent)] outline-none hover:underline focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
                    >
                      {u.cta}
                      <ChevronRight className="size-4" />
                    </Link>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Getting started */}
      <section aria-labelledby="hiw-start" className="flex flex-col gap-3">
        <h2 id="hiw-start" className="text-lg font-semibold tracking-tight">
          Get started in three steps
        </h2>
        <Card>
          <CardBody className="flex flex-col gap-5">
            <ol className="flex flex-col gap-4">
              {STEPS.map((step, i) => (
                <li key={step.title} className="flex gap-4">
                  <span
                    aria-hidden
                    className="flex size-9 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] text-sm font-semibold tabular-nums text-[var(--accent)]"
                  >
                    {i + 1}
                  </span>
                  <div className="min-w-0 pt-1">
                    <p className="font-medium">{step.title}</p>
                    <p className="mt-0.5 text-sm leading-relaxed text-[var(--muted-fg)]">
                      {step.body}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
            <Link
              href="/settings/agents"
              className="inline-flex h-9 w-fit items-center justify-center gap-2 rounded-lg bg-[var(--accent)] px-4 text-sm font-medium text-[var(--accent-fg)] shadow-[var(--shadow-xs)] outline-none transition-colors hover:bg-[var(--accent-hover)] focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
            >
              Register your first agent
              <ArrowRight className="size-4" />
            </Link>
          </CardBody>
        </Card>
      </section>
    </article>
  );
}
