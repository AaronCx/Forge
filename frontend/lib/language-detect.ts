/**
 * Maps file extensions to CodeMirror language support.
 */

import type { Extension } from "@codemirror/state";

const languageMap: Record<string, () => Promise<Extension>> = {
  js: () => import("@codemirror/lang-javascript").then((m) => m.javascript()),
  jsx: () => import("@codemirror/lang-javascript").then((m) => m.javascript({ jsx: true })),
  ts: () => import("@codemirror/lang-javascript").then((m) => m.javascript({ typescript: true })),
  tsx: () =>
    import("@codemirror/lang-javascript").then((m) => m.javascript({ jsx: true, typescript: true })),
  py: () => import("@codemirror/lang-python").then((m) => m.python()),
  json: () => import("@codemirror/lang-json").then((m) => m.json()),
  md: () => import("@codemirror/lang-markdown").then((m) => m.markdown()),
  markdown: () => import("@codemirror/lang-markdown").then((m) => m.markdown()),
  html: () => import("@codemirror/lang-html").then((m) => m.html()),
  htm: () => import("@codemirror/lang-html").then((m) => m.html()),
  css: () => import("@codemirror/lang-css").then((m) => m.css()),
  scss: () => import("@codemirror/lang-css").then((m) => m.css()),
};

export async function getLanguageExtension(filename: string): Promise<Extension | null> {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  const loader = languageMap[ext];
  if (!loader) return null;
  return loader();
}
