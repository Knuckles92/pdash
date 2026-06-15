import { LayoutDashboard, Columns2, Inbox, Rows3, Table2, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { CommandCenterLayout } from "./CommandCenterLayout";
import { MasterDetailLayout } from "./MasterDetailLayout";
import { PowerGridLayout } from "./PowerGridLayout";
import { RailCardsLayout } from "./RailCardsLayout";
import { TriageInboxLayout } from "./TriageInboxLayout";
import type { ApprovalLayoutProps } from "./shared";

export type ApprovalLayout = {
  id: string;
  name: string;
  icon: LucideIcon;
  Component: (props: ApprovalLayoutProps) => ReactNode;
};

/** The promoted layouts, in switcher order. "rail" is the default. */
export const APPROVAL_LAYOUTS: ApprovalLayout[] = [
  { id: "rail", name: "Cards", icon: Rows3, Component: RailCardsLayout },
  { id: "inbox", name: "Inbox", icon: Inbox, Component: TriageInboxLayout },
  { id: "split", name: "Split", icon: Columns2, Component: MasterDetailLayout },
  { id: "command", name: "Command", icon: LayoutDashboard, Component: CommandCenterLayout },
  { id: "grid", name: "Grid", icon: Table2, Component: PowerGridLayout },
];

export const DEFAULT_LAYOUT_ID = "rail";

export function isLayoutId(id: string): boolean {
  return APPROVAL_LAYOUTS.some((l) => l.id === id);
}

export function getLayout(id: string): ApprovalLayout {
  return APPROVAL_LAYOUTS.find((l) => l.id === id) ?? APPROVAL_LAYOUTS[0]!;
}

export type { ApprovalLayoutProps } from "./shared";
export { buildRows } from "./shared";
export type { ApprovalRowVM } from "./shared";
