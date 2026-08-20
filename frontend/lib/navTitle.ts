/** Human label for the current route — used by the mobile top bar. */

export function navTitleFromPath(
  pathname: string,
  pages: { slug: string; name: string }[],
): string {
  if (pathname.startsWith("/approvals")) return "Approvals";
  if (pathname.startsWith("/activity")) return "Activity";
  if (pathname.startsWith("/settings")) return "Settings";
  if (pathname.startsWith("/how-it-works")) return "Guide";
  if (pathname === "/" || pathname === "") {
    return pages.find((p) => p.slug === "home")?.name ?? "Home";
  }
  if (pathname.startsWith("/pages/")) {
    const slug = pathname.split("/")[2] ?? "";
    return pages.find((p) => p.slug === slug)?.name ?? slug;
  }
  return "pdash";
}
