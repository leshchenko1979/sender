const SUPABASE_URL = window.location.origin + '/supabase';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImJ2emZiY3Z6aWJvamx5dWdxYXNkIiwicm9sZSI6ImFub24iLCJpYXQiOjE2ODI4MzE2NDEsImV4cCI6MTk5ODQwNzY0MX0.w3_Apu0RkLvZ16eTV9HSUtETCmA1lVhHu6i2ZESCdes';

const REST_BASE = `${SUPABASE_URL}/rest/v1`;

const headers = {
    'apikey': SUPABASE_ANON_KEY,
    'Authorization': `Bearer ${SUPABASE_ANON_KEY}`,
};

export async function query(table, params = {}) {
    const url = new URL(`${REST_BASE}/${table}`);
    for (const [k, v] of Object.entries(params)) {
        url.searchParams.set(k, v);
    }
    const resp = await fetch(url, { headers });
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}`);
    return resp.json();
}
