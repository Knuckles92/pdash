/**
 * Inline script that runs before paint to apply the persisted theme,
 * avoiding a flash of incorrect color scheme.
 */
const SCRIPT = `(() => {
  try {
    const stored = localStorage.getItem('pdash-theme');
    if (stored === 'light' || stored === 'dark') {
      document.documentElement.setAttribute('data-theme', stored);
    }
  } catch (e) { /* ignore */ }
})();`;

export function ThemeScript() {
  return <script dangerouslySetInnerHTML={{ __html: SCRIPT }} />;
}
