"use client";

import { useEffect, useRef, useCallback } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers, highlightActiveLine, drawSelection } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { oneDark } from "@codemirror/theme-one-dark";
import { bracketMatching } from "@codemirror/language";
import { autocompletion } from "@codemirror/autocomplete";
import { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
import { getLanguageExtension } from "@/lib/language-detect";

interface CodeEditorProps {
  content: string;
  filename: string;
  onChange: (content: string) => void;
  onSave: () => void;
}

export function CodeEditor({ content, filename, onChange, onSave }: CodeEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);

  onChangeRef.current = onChange;
  onSaveRef.current = onSave;

  const setupEditor = useCallback(async () => {
    if (!containerRef.current) return;

    // Clean up previous instance
    if (viewRef.current) {
      viewRef.current.destroy();
      viewRef.current = null;
    }

    // Load language extension
    const langExt = await getLanguageExtension(filename);

    const extensions = [
      lineNumbers(),
      highlightActiveLine(),
      drawSelection(),
      bracketMatching(),
      history(),
      autocompletion(),
      highlightSelectionMatches(),
      oneDark,
      keymap.of([
        ...defaultKeymap,
        ...historyKeymap,
        ...searchKeymap,
        {
          key: "Mod-s",
          run: () => {
            onSaveRef.current();
            return true;
          },
        },
      ]),
      EditorView.updateListener.of((update) => {
        if (update.docChanged) {
          onChangeRef.current(update.state.doc.toString());
        }
      }),
      EditorView.theme({
        "&": { height: "100%", fontSize: "13px" },
        ".cm-scroller": { overflow: "auto" },
        ".cm-content": { fontFamily: "'SF Mono', 'Fira Code', 'Cascadia Code', monospace" },
        ".cm-gutters": { fontFamily: "'SF Mono', monospace" },
      }),
    ];

    if (langExt) extensions.push(langExt);

    const state = EditorState.create({
      doc: content,
      extensions,
    });

    viewRef.current = new EditorView({
      state,
      parent: containerRef.current,
    });
    // setupEditor reads `content` only as the editor's initial doc; live updates
    // are handled by the separate effect below, so we deliberately re-create only
    // when the filename changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filename]);

  useEffect(() => {
    setupEditor();
    return () => {
      viewRef.current?.destroy();
      viewRef.current = null;
    };
  }, [setupEditor]);

  // Update content when it changes externally (e.g., WebSocket)
  useEffect(() => {
    if (!viewRef.current) return;
    const currentContent = viewRef.current.state.doc.toString();
    if (currentContent !== content) {
      viewRef.current.dispatch({
        changes: { from: 0, to: currentContent.length, insert: content },
      });
    }
  }, [content]);

  return <div ref={containerRef} className="h-full w-full overflow-hidden" />;
}
