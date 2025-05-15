const API_URL = 'https://sqlvalidatorapi.onrender.com';

export const validateQuery = async (query: string): Promise<string[]> => {
  const res = await fetch(`${API_URL}/api/query/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });

  return await res.json();
};