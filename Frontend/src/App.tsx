import { useState } from 'react'
import { validateQuery } from './api/queryApi';
import CodeMirror from '@uiw/react-codemirror';
import { sql } from '@codemirror/lang-sql';
import { linter } from '@codemirror/lint';
import type { Diagnostic } from '@codemirror/lint';
import { GutterMarker, gutter } from '@codemirror/view';
import { RangeSetBuilder, RangeSet } from '@codemirror/state';
import type { EditorView } from '@codemirror/view';
import { getAiSuggestion } from './api/aiApi';

function App() {
  const [query, setQuery] = useState('');
  const [issues, setIssues] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [diagnostics, setDiagnostics] = useState<Diagnostic[]>([]);
  const [suggestedFix, setSuggestedFix] = useState('');


  const handleSuggestFix = async () => {
    try {
      const suggestion = await getAiSuggestion(query, issues);
      setSuggestedFix(suggestion?.trim() || 'No suggestion returned.');
    } catch (error) {
      console.error('AI suggestion error:', error);
      setSuggestedFix('⚠️ AI suggestion failed. Please try again later.');
    }
  };  


  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const result = await validateQuery(query); // backend returns ["Line 3: ..."]
      setIssues(result);
  
      const lines = query.split('\n');
      const newDiagnostics: Diagnostic[] = [];
  
      result.forEach((msg) => {
        const match = msg.match(/^Line (\d+):/);
        if (match) {
          const lineNumber = parseInt(match[1], 10);
          const line = lines[lineNumber - 1] || '';
          const start = lines.slice(0, lineNumber - 1).reduce((sum, l) => sum + l.length + 1, 0);
  
          newDiagnostics.push({
            from: start,
            to: start + line.length,
            severity: 'warning',
            message: msg.replace(/^Line \d+:\s*/, ''),
          });
        }
      });
  
      setDiagnostics(newDiagnostics);
    } catch (err) {
      console.error(err);
      setIssues(['An error occurred while validating.']);
      setDiagnostics([]);
    } finally {
      setLoading(false);
    }
  };

  class WarningMarker extends GutterMarker {
    toDOM() {
      const marker = document.createElement('div');
      marker.textContent = '⚠️';
      marker.style.fontSize = '12px';
      marker.title = 'Lint issue';
      return marker;
    }
  }
  
  const warningMarker = new WarningMarker();

  const customLinter = () =>
    linter(() => diagnostics, {
      // Optional, but we still use linter core
      delay: 10,
    });
  
  const customGutter = gutter({
    class: 'cm-lint-gutter',
    markers: (view: EditorView): RangeSet<GutterMarker> => {
      const builder = new RangeSetBuilder<GutterMarker>();
      const seenLines = new Set<number>();
  
      diagnostics.forEach((d) => {
        const line = view.state.doc.lineAt(d.from);
        if (!seenLines.has(line.number)) {
          builder.add(line.from, line.from, warningMarker);
          seenLines.add(line.number);
        }
      });
  
      return builder.finish();
    },
    initialSpacer: () => warningMarker,
  });
    
  return (
    <div style={{ height: '100vh', width: '100vw', display: 'flex', flexDirection: 'column' }}>
      {/* Header Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '12px 24px',
          backgroundColor: '#f9fafb',
          borderBottom: '1px solid #e5e7eb',
        }}
      >
        <h1 style={{ fontSize: 24, fontWeight: 'bold' }}>SQL Validator Dashboard</h1>
        <button
          onClick={handleSubmit}
          style={{
            background: '#2563eb',
            color: 'white',
            padding: '8px 16px',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
          }}
        >
          {loading ? 'Validating...' : 'Validate'}
        </button>
        <button
          onClick={handleSuggestFix}
          disabled={issues.length === 0}
          style={{
            background: issues.length === 0 ? '#d1d5db' : '#10b981',
            color: 'white',
            padding: '8px 16px',
            border: 'none',
            borderRadius: 4,
            cursor: issues.length === 0 ? 'not-allowed' : 'pointer',
            marginLeft: '12px',
          }}
        >
          Suggest Fix
        </button>
      </div>


      <div className="main-content">
        
        {/* Editor Left Panel */}
        <div className="editor-panel">
          <label style={{ fontWeight: 'bold', marginBottom: 8, display: 'block' }}>
            SQL Query:
          </label>
          <CodeMirror
            value={query}
            height="100%"
            width="100%"
            extensions={[sql(), customLinter(), customGutter]}
            onChange={(value) => {
              setQuery(value);
              setSuggestedFix('');
              setIssues([]);
              setDiagnostics([]);
            }}
            theme="light"
          />
        </div>

        {/* Issues + Fix Right Panel */}
        <div className="results-panel">
          <div className="issues-panel">
            <label style={{ fontWeight: 'bold', marginBottom: 8, display: 'block' }}>
              Issues Found:
            </label>
            {issues.length === 0 ? (
              <p style={{ color: '#6b7280' }}>No issues found.</p>
            ) : (
              <ul
                style={{
                  color: '#dc2626',
                  background: '#fef2f2',
                  padding: 12,
                  borderRadius: 4,
                  marginBottom: 16,
                }}
              >
                {issues.map((issue, idx) => (
                  <li key={idx}>{issue}</li>
                ))}
              </ul>
            )}
          </div>

          <div className="fix-panel">
            <label style={{ fontWeight: 'bold', marginBottom: 8, display: 'block' }}>
              Suggested Fix:
            </label>
            <CodeMirror
              value={suggestedFix}
              height="300px"
              width="100%"
              extensions={[sql()]}
              onChange={() => {}}
              theme="light"
              editable={false}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;


