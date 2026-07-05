"use client";

import { GroupedInbox } from "./GroupedInbox";
import type { ApprovalLayoutProps } from "./shared";

/** Triage Inbox — collapsible agent groups of dense, color-railed rows. */
export function TriageInboxLayout(props: ApprovalLayoutProps) {
  return <GroupedInbox {...props} />;
}
