import re

with open("frontend/src/app/page.tsx", "r") as f:
    page_ts = f.read()
page_ts = re.sub(r'useState<any \| null>', r'useState<Record<string, unknown> | null>', page_ts)
page_ts = re.sub(r'\(prev: any\)', r'(prev: Record<string, unknown> | null)', page_ts)
with open("frontend/src/app/page.tsx", "w") as f:
    f.write(page_ts)

with open("frontend/src/app/settings/page.tsx", "r") as f:
    settings_ts = f.read()
settings_ts = re.sub(r'useState<any \| null>', r'useState<Record<string, unknown> | null>', settings_ts)
with open("frontend/src/app/settings/page.tsx", "w") as f:
    f.write(settings_ts)
