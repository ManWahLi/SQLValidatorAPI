export const validateQuery = async (query: string): Promise<string[]> => {
  const res = await fetch('http://127.0.0.1:8001/api/query/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });

  return await res.json();
};
