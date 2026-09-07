import { it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EditorView } from '@codemirror/view';
import { indentWithTab, insertNewlineAndIndent } from '@codemirror/commands';
import { syntaxTree } from '@codemirror/language';
import CodeEditor from './CodeEditor.jsx';

it('renders highlighted multiline code and line numbers, supports indentation, and blocks read-only edits', () => {
  const onChange = vi.fn();
  const { container, rerender } = render(<CodeEditor value={'const total = 1;\nreturn total;'} editable onChange={onChange} />);
  const content = screen.getByRole('textbox', { name: 'Shared code' });
  const view = EditorView.findFromDOM(content);
  expect(container.querySelectorAll('.cm-line')).toHaveLength(2);
  expect(container.querySelector('.cm-lineNumbers')).toHaveTextContent('2');
  expect(container.querySelector('.cm-line span')).not.toBeNull();
  view.dispatch({ selection: { anchor: 0 } });
  expect(indentWithTab.run(view)).toBe(true);
  expect(view.state.doc.toString()).toMatch(/^\s+const/);
  expect(onChange).toHaveBeenCalled();
  insertNewlineAndIndent(view);
  expect(view.state.doc.lines).toBe(3);
  rerender(<CodeEditor value="const total = 2;" editable={false} onChange={onChange} />);
  expect(view.state.readOnly).toBe(true);
  const before = view.state.doc.toString();
  indentWithTab.run(view);
  expect(view.state.doc.toString()).toBe(before);
  expect(content).toHaveAttribute('contenteditable', 'false');
});

it('switches Python and JavaScript highlighting without replacing code or selection', () => {
  const onChange = vi.fn();
  const value = 'def greet(name):\n    return "Hello"';
  const { container, rerender } = render(<CodeEditor value={value} editable language="python" onChange={onChange} />);
  const view = EditorView.findFromDOM(screen.getByRole('textbox', { name: 'Shared code' }));
  expect(syntaxTree(view.state).toString()).toContain('FunctionDefinition');
  expect(container.querySelector('.cm-line span')).toHaveTextContent('def');
  view.dispatch({ selection: { anchor: 4 } });
  rerender(<CodeEditor value={value} editable language="javascript" onChange={onChange} />);
  expect(syntaxTree(view.state).topNode.name).toBe('Script');
  expect(view.state.doc.toString()).toBe(value);
  expect(view.state.selection.main.anchor).toBe(4);
  rerender(<CodeEditor value={value} editable language="python" onChange={onChange} />);
  expect(syntaxTree(view.state).toString()).toContain('FunctionDefinition');
  expect(onChange).not.toHaveBeenCalled();
});
