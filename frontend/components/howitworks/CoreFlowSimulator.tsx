"use client";

import { Check, ChevronLeft, ChevronRight, Pause, Play } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { cn } from "@/lib/cn";

import { OUTCOMES, STAGES, outcomeById, toneTint, type OutcomeId } from "./simulatorModel";
import { DashboardStage, McpCallStage, ReviewStage, RuleMatchStage } from "./SimulatorStages";

const AUTOPLAY_MS = 3400;

/**
 * The centerpiece: a steppable pipeline (a WAI-ARIA tablist) crossed with a
 * persistent "outcome" switcher (a radiogroup). The four steps are the tabs;
 * the outcome decides which branch the engine takes, so the user can scrub the
 * SAME proposed change through auto-approve / pending / deny and watch the
 * dashboard apply it — or visibly not. All motion is CSS, gated on
 * prefers-reduced-motion; autoplay is opt-in and hidden under reduced motion.
 */
export function CoreFlowSimulator() {
  const [activeStep, setActiveStep] = useState(0);
  const [outcome, setOutcome] = useState<OutcomeId>("pending");
  const [approved, setApproved] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [reduced, setReduced] = useState(false);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Has the proposed write actually landed on the dashboard?
  const applied = outcome === "auto" || (outcome === "pending" && approved);

  // A new branch is a fresh scenario — forget any prior "approve" demo action.
  useEffect(() => setApproved(false), [outcome]);

  // Respect reduced-motion: drives whether autoplay is offered at all.
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => {
      setReduced(mq.matches);
      // The Play/Pause control is hidden under reduced motion, so don't leave
      // autoplay stuck "on" with no way to turn it off.
      if (mq.matches) setPlaying(false);
    };
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  const goTo = useCallback((i: number, opts?: { focus?: boolean }) => {
    const next = (i + STAGES.length) % STAGES.length;
    setActiveStep(next);
    if (opts?.focus) tabRefs.current[next]?.focus();
  }, []);

  // Opt-in autoplay; never runs (nor renders its control) under reduced motion.
  useEffect(() => {
    if (!playing || reduced) return;
    const t = setInterval(() => setActiveStep((s) => (s + 1) % STAGES.length), AUTOPLAY_MS);
    return () => clearInterval(t);
  }, [playing, reduced]);

  const stopPlay = () => setPlaying(false);

  // Buttons/dots/outcome: change step without yanking focus onto the rail.
  const jump = (i: number) => {
    stopPlay();
    goTo(i);
  };

  // APG tabs: automatic activation — arrowing moves focus AND selects (panels
  // render instantly, so this is the recommended variant).
  const onRailKeyDown = (e: React.KeyboardEvent) => {
    let next = activeStep;
    switch (e.key) {
      case "ArrowRight":
      case "ArrowDown":
        next = activeStep + 1;
        break;
      case "ArrowLeft":
      case "ArrowUp":
        next = activeStep - 1;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = STAGES.length - 1;
        break;
      default:
        return;
    }
    e.preventDefault();
    stopPlay();
    goTo(next, { focus: true });
  };

  const handleApprove = () => {
    stopPlay();
    setApproved(true);
    // The panel (and the Approve button inside it) is keyed/remounted on this
    // change, so land focus on the step-4 tab, which lives outside the panel
    // and survives — otherwise focus would fall to <body>.
    goTo(3, { focus: true });
  };

  const current = STAGES[activeStep] ?? STAGES[0];
  const outcomeMeta = outcomeById(outcome);
  const OutcomeIcon = outcomeMeta.icon;
  // The connector track spans the node centres (12.5% … 87.5% of the rail).
  const progressPct = (activeStep / (STAGES.length - 1)) * 75;

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-col gap-5 p-5 sm:p-6">
        {/* Pipeline rail = tablist */}
        <div className="relative">
          <div
            aria-hidden
            className="absolute left-[12.5%] right-[12.5%] top-5 hidden h-0.5 bg-[var(--border)] sm:block"
          />
          <div
            aria-hidden
            className="absolute left-[12.5%] top-5 hidden h-0.5 bg-[var(--accent)] transition-[width] duration-500 ease-out motion-reduce:transition-none sm:block"
            style={{ width: `${progressPct}%` }}
          />
          <div
            role="tablist"
            aria-label="Approval flow steps"
            aria-orientation="horizontal"
            onKeyDown={onRailKeyDown}
            className="relative flex gap-3 overflow-x-auto pb-1 sm:grid sm:grid-cols-4 sm:gap-2 sm:overflow-visible"
          >
            {STAGES.map((s, i) => {
              const Icon = s.icon;
              const done = i < activeStep;
              const active = i === activeStep;
              return (
                <button
                  key={s.id}
                  role="tab"
                  id={`hiw-tab-${s.id}`}
                  aria-selected={active}
                  aria-controls="hiw-panel"
                  tabIndex={active ? 0 : -1}
                  ref={(el) => {
                    tabRefs.current[i] = el;
                  }}
                  onClick={() => jump(i)}
                  className="group flex min-w-[6.5rem] shrink-0 snap-start flex-col items-center gap-2 rounded-lg p-2 text-center outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)] sm:min-w-0"
                >
                  <span
                    className={cn(
                      "flex size-10 items-center justify-center rounded-full border transition-colors",
                      done || active
                        ? "border-transparent bg-[var(--accent)] text-[var(--accent-fg)]"
                        : "border-[var(--border)] bg-[var(--card)] text-[var(--muted-fg)] group-hover:text-[var(--fg)]",
                      active && "ring-2 ring-[var(--accent)] ring-offset-2 ring-offset-[var(--card)]",
                    )}
                  >
                    {done ? <Check className="size-5" /> : <Icon className="size-5" />}
                  </span>
                  <span
                    className={cn(
                      "text-xs leading-tight",
                      active ? "font-semibold text-[var(--fg)]" : "text-[var(--muted-fg)]",
                    )}
                  >
                    <span className="tabular-nums">{i + 1}</span> · {s.rail}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Toolbar: outcome switcher + autoplay */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-y border-[var(--border)] py-3">
          <fieldset className="flex flex-wrap items-center gap-2">
            <legend className="sr-only">Engine outcome</legend>
            <span className="text-xs font-medium text-[var(--muted-fg)]">If a rule says…</span>
            <div className="inline-flex rounded-lg border border-[var(--border)] bg-[var(--muted)]/60 p-0.5 shadow-[var(--shadow-xs)]">
              {OUTCOMES.map((o) => {
                const on = o.id === outcome;
                const Icon = o.icon;
                return (
                  <label
                    key={o.id}
                    className={cn(
                      "relative inline-flex cursor-pointer items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                      !on && "text-[var(--muted-fg)] hover:text-[var(--fg)]",
                    )}
                    style={on ? toneTint(o.tone, { bg: 16, border: 0 }) : undefined}
                  >
                    <input
                      type="radio"
                      name="hiw-outcome"
                      value={o.id}
                      checked={on}
                      onChange={() => {
                        stopPlay();
                        setOutcome(o.id);
                      }}
                      className="peer sr-only"
                    />
                    <span className="pointer-events-none absolute inset-0 rounded-md peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--accent)]" />
                    <Icon className="size-3.5" style={on ? { color: `var(--${o.tone})` } : undefined} />
                    {o.label}
                  </label>
                );
              })}
            </div>
          </fieldset>
          {!reduced && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setPlaying((p) => !p)}
              aria-pressed={playing}
            >
              {playing ? (
                <>
                  <Pause className="size-4" /> Pause
                </>
              ) : (
                <>
                  <Play className="size-4" /> Play tour
                </>
              )}
            </Button>
          )}
        </div>

        {/* Demo panel — keyed so the enter animation re-fires on every change */}
        <div className="min-h-[280px]">
          <div
            key={`${activeStep}-${outcome}-${approved}`}
            id="hiw-panel"
            role="tabpanel"
            tabIndex={0}
            aria-labelledby={`hiw-tab-${current.id}`}
            className="hiw-panel-enter rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--card)]"
          >
            <h3 className="text-base font-semibold tracking-tight">{current.title}</h3>
            <p className="mb-4 mt-1 text-sm leading-relaxed text-[var(--muted-fg)]">
              {current.explain}
            </p>
            {activeStep === 0 && <McpCallStage />}
            {activeStep === 1 && <RuleMatchStage outcome={outcome} />}
            {activeStep === 2 && (
              <ReviewStage outcome={outcome} approved={approved} onApprove={handleApprove} />
            )}
            {activeStep === 3 && <DashboardStage outcome={outcome} applied={applied} />}
          </div>
        </div>

        {/* Step controls */}
        <div className="flex items-center justify-between gap-3">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => jump(activeStep - 1)}
            disabled={activeStep === 0}
          >
            <ChevronLeft className="size-4" /> Back
          </Button>
          <div className="flex items-center gap-2" role="presentation">
            {STAGES.map((s, i) => (
              <button
                key={s.id}
                type="button"
                aria-label={`Go to step ${i + 1}: ${s.rail}`}
                aria-current={i === activeStep ? "step" : undefined}
                onClick={() => jump(i)}
                className={cn(
                  "size-2.5 rounded-full transition-colors",
                  i === activeStep
                    ? "bg-[var(--accent)]"
                    : "bg-[var(--border)] hover:bg-[var(--muted-fg)]",
                )}
              />
            ))}
          </div>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => jump(activeStep + 1)}
            disabled={activeStep === STAGES.length - 1}
          >
            Next <ChevronRight className="size-4" />
          </Button>
        </div>

        {/* Persistent semantics caption — the active branch is emphasised */}
        <p className="rounded-lg bg-[var(--muted)] px-3 py-2 text-xs leading-relaxed text-[var(--muted-fg)]">
          <span
            className="inline-flex items-center gap-1 font-medium"
            style={{ color: `var(--${outcomeMeta.tone})` }}
          >
            <OutcomeIcon className="size-3.5" />
            {outcomeMeta.label}:
          </span>{" "}
          {outcomeMeta.blurb}
        </p>

        <div aria-live="polite" className="sr-only">
          Step {activeStep + 1} of {STAGES.length}: {current.title}. Outcome: {outcomeMeta.label}.
          {activeStep === 3
            ? applied
              ? " Change applied to the dashboard."
              : " Proposed change not applied."
            : ""}
        </div>
      </div>
    </Card>
  );
}
