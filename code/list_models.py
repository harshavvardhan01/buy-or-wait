"""Diagnostic: which models does this API key actually expose?"""
import os

import requests

key = os.environ.get("GEMINI_API_KEY")
if not key:
    raise SystemExit("GEMINI_API_KEY not set in this process")

for version in ("v1beta", "v1"):
    url = f"https://generativelanguage.googleapis.com/{version}/models"
    resp = requests.get(url, params={"key": key}, timeout=30)
    print(f"\n=== {version} -> HTTP {resp.status_code} ===")
    if resp.status_code != 200:
        print(resp.text[:300])
        continue
    for model in resp.json().get("models", []):
        if "generateContent" in model.get("supportedGenerationMethods", []):
            print(" ", model["name"].replace("models/", ""))