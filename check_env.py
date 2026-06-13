from dotenv import load_dotenv
import os

load_dotenv()

keys = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "KIMI_API_KEY",
    "KIMI_API_BASE",
    "TOKENROUTER_API_KEY",
    "TOKENROUTER_API_BASE",
]

for k in keys:
    v = os.environ.get(k, "")
    if v:
        print(f"{k} = {v[:10]}... ({len(v)} chars)")
    else:
        print(f"{k} = *** MISSING ***")
