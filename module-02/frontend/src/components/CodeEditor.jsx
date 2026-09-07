import { useEffect, useRef } from 'react';
import { Compartment, EditorState } from '@codemirror/state';
import { EditorView, lineNumbers, keymap, drawSelection } from '@codemirror/view';
import { defaultKeymap, indentWithTab } from '@codemirror/commands';
import { syntaxHighlighting, defaultHighlightStyle, indentOnInput } from '@codemirror/language';
import { javascript } from '@codemirror/lang-javascript';
import { python } from '@codemirror/lang-python';

export default function CodeEditor({ value, editable, onChange, language = 'javascript' }) {
  const host = useRef(null);
  const editor = useRef(null);
  const callback = useRef(onChange);
  callback.current = onChange;
  const syntax = useRef(new Compartment());
  const permission = useRef(new Compartment());
  const external = useRef(false);
  useEffect(() => {
    const view = new EditorView({ parent: host.current, state: EditorState.create({
      doc: '', extensions: [lineNumbers(), drawSelection(), syntax.current.of([]), indentOnInput(),
        syntaxHighlighting(defaultHighlightStyle), keymap.of([...defaultKeymap, indentWithTab]),
        permission.current.of([]),
        EditorView.contentAttributes.of({ 'aria-label': 'Shared code', role: 'textbox', 'aria-multiline': 'true', tabindex: '0' }),
        EditorView.updateListener.of(update => {
          if (update.docChanged && !external.current) callback.current(update.state.doc.toString());
        }),
        EditorView.theme({ '&': { height: '100%', fontSize: '14px' }, '.cm-scroller': { overflow: 'auto', fontFamily: 'Consolas, monospace' }, '.cm-content': { minHeight: '360px', padding: '20px 0' }, '.cm-gutters': { background: '#f4f6f5', color: '#82918d', border: 'none' }, '.cm-line': { padding: '0 16px' }, '&.cm-focused': { outline: '2px solid #258577', outlineOffset: '-2px' } }),
      ],
    }) });
    editor.current = view;
    return () => view.destroy();
  }, []);
  useEffect(() => {
    const view = editor.current;
    if (view.state.doc.toString() !== value) {
      external.current = true;
      view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: value } });
      external.current = false;
    }
  }, [value]);
  useEffect(() => {
    editor.current.dispatch({ effects: permission.current.reconfigure([
      EditorState.readOnly.of(!editable), EditorView.editable.of(editable),
      EditorView.contentAttributes.of({ 'aria-readonly': String(!editable) }),
    ]) });
  }, [editable]);
  useEffect(() => {
    editor.current.dispatch({ effects: syntax.current.reconfigure(language === 'python' ? python() : javascript()) });
  }, [language]);
  return <div className="code-editor" ref={host} />;
}
