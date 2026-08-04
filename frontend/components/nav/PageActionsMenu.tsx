"use client";

import { ListChecks, MoreHorizontal, Settings, ShieldCheck, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { AgentAccessSheet } from "@/components/page/AgentAccessSheet";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import type { Page } from "@/lib/api";
import { api, errorMessage } from "@/lib/api";
import { cn } from "@/lib/cn";

import { usePages } from "./PagesProvider";

type PageActionsMenuProps = {
  page: Page;
  buttonClassName?: string;
  buttonSizeClassName?: string;
  onAction?: () => void;
};

export function PageActionsMenu({
  page,
  buttonClassName,
  buttonSizeClassName = "size-7",
  onAction,
}: PageActionsMenuProps) {
  const [open, setOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const { removePage } = usePages();
  const rootRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname() ?? "/";
  const router = useRouter();
  const isHome = page.type === "home";
  const pageHref = page.slug === "home" ? "/" : `/pages/${page.slug}`;
  const rulesHref = `/settings/rules?page_id=${encodeURIComponent(page.id)}`;

  useEffect(() => {
    if (!open) return;

    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  async function handleDelete() {
    if (isHome) return;

    setDeleting(true);
    try {
      await api.deletePage(page.id);
      // Drop the entry from the nav immediately — don't rely on the
      // router.refresh() round-trip landing to update the page list.
      removePage(page.id);
      toast.success("Page deleted");
      setOpen(false);
      setConfirmOpen(false);
      onAction?.();
      if (pathname === pageHref) {
        router.push("/");
      }
      router.refresh();
    } catch (err) {
      toast.error(errorMessage(err, "Delete failed"));
    } finally {
      setDeleting(false);
    }
  }

  function closeAfterAction() {
    setOpen(false);
    onAction?.();
  }

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          setOpen((value) => !value);
        }}
        className={cn(
          "inline-flex shrink-0 items-center justify-center rounded-lg text-[var(--muted-fg)] transition-colors hover:bg-[var(--card)] hover:text-[var(--fg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg)]",
          buttonSizeClassName,
          buttonClassName,
        )}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Open settings for ${page.name}`}
        title={`Open settings for ${page.name}`}
      >
        <MoreHorizontal className="size-4" />
      </button>

      {open && (
        <div
          className="absolute right-1 top-full z-40 mt-1 w-48 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card)] p-1.5 text-sm shadow-[var(--shadow-md)] anim-pop-in"
          role="menu"
        >
          <Link
            href="/settings/pages"
            onClick={closeAfterAction}
            className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-[var(--fg)] transition-colors hover:bg-[var(--muted)]"
            role="menuitem"
          >
            <Settings className="size-4" />
            Page settings
          </Link>
          <button
            type="button"
            onClick={() => {
              // Keep the sheet mounted: don't fire onAction here, since in the
              // mobile drawer that would unmount this menu (and the sheet with it).
              setOpen(false);
              setAccessOpen(true);
            }}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[var(--fg)] transition-colors hover:bg-[var(--muted)]"
            role="menuitem"
          >
            <ShieldCheck className="size-4" />
            Agent access
          </button>
          <Link
            href={rulesHref}
            onClick={closeAfterAction}
            className="flex items-center gap-2 rounded-lg px-2.5 py-2 text-[var(--fg)] transition-colors hover:bg-[var(--muted)]"
            role="menuitem"
          >
            <ListChecks className="size-4" />
            Approval rules
          </Link>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              setConfirmOpen(true);
            }}
            disabled={isHome || deleting}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-[var(--danger)] transition-colors hover:bg-[var(--danger-soft)] disabled:pointer-events-none disabled:opacity-50"
            role="menuitem"
            title={isHome ? "Cannot delete home" : "Delete page"}
          >
            <Trash2 className="size-4" />
            {deleting ? "Deleting" : "Delete page"}
          </button>
        </div>
      )}
      <AgentAccessSheet
        page={page}
        open={accessOpen}
        onClose={() => {
          setAccessOpen(false);
          onAction?.();
        }}
      />
      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title="Delete page?"
        description={`"${page.name}" and its modules will be soft-deleted.`}
        confirmLabel="Delete page"
        loadingLabel="Deleting"
        icon={<Trash2 className="size-4" />}
        loading={deleting}
        onConfirm={handleDelete}
      >
        <p className="text-sm text-[var(--muted-fg)]">
          This removes the page from navigation and cascades to its modules. The home page cannot
          be deleted.
        </p>
      </ConfirmDialog>
    </div>
  );
}
