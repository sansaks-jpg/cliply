import re

with open("backend/app/main.py", "r") as f:
    content = f.read()

# Add Request import if missing
if "from fastapi import Request" not in content:
    # Find the fastapi import line
    content = re.sub(r'from fastapi import FastAPI', 'from fastapi import FastAPI, Request', content)

# Add middleware after CORS middleware
middleware_code = """
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

"""

if "add_security_headers" not in content:
    cors_end = content.find("app.include_router(tasks.router)")
    content = content[:cors_end] + middleware_code + content[cors_end:]

with open("backend/app/main.py", "w") as f:
    f.write(content)
