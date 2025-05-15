const API_URL = import.meta.env.VITE_API_URL

export const validateQuery = async (query: string): Promise<string[]> => {
  const res = await fetch(`${API_URL}/api/query/validate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });

  return await res.json();
};