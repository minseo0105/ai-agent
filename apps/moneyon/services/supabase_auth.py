"""Server-only authentication shared by all Supabase REST consumers."""
def supabase_headers(key, *, prefer=None):
    if not key or any(c.isspace() for c in key):
        raise ValueError("Invalid backend Supabase credential")
    if key.startswith('sb_publishable_'):
        raise ValueError("Backend requires a server credential")
    headers = {'apikey': key, 'Content-Type': 'application/json'}
    if not key.startswith('sb_secret_'):
        headers['Authorization'] = 'Bearer ' + key
    if prefer:
        headers['Prefer'] = prefer
    return headers
