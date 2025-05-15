export const getAiSuggestion = async (query: string, issues: string[]): Promise<string> => {
  try {
    const res = await fetch('http://127.0.0.1:8001/api/query/suggestfix', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, issues }),
    });

    if (!res.ok) {
      const errorText = await res.text();
      throw new Error(`API error (${res.status}): ${errorText}`);
    }

    const data = await res.json();

    // Since FastAPI returns either a string or an object with "response"
    if (typeof data === 'string') return data;
    return data.response || data.message || '⚠️ No suggestion returned.';
  } catch (error) {
    console.error('getAiSuggestion failed:', error);
    return '⚠️ Error fetching AI suggestion.';
  }
};
