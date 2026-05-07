from fastapi import FastAPI, HTTPException, Header, Depends, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
import sqlite3, secrets
from datetime import datetime
import csv
from io import StringIO
from collections import defaultdict

app = FastAPI()
security = HTTPBasic()

# --- SECURITY & DATABASE ---
def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    if not (secrets.compare_digest(credentials.username, "admin") and 
            secrets.compare_digest(credentials.password, "Innovate2026!")):
        raise HTTPException(status_code=401, detail="Unauthorized", headers={"WWW-Authenticate": "Basic"})
    return credentials.username

def init_db():
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY, employee_id TEXT, timestamp TEXT, action TEXT, lat REAL, lon REAL)')
    cursor.execute('CREATE TABLE IF NOT EXISTS leaves (id INTEGER PRIMARY KEY, employee_id TEXT, dates TEXT, reason TEXT, status TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- PYDANTIC MODELS ---
class LeaveRequest(BaseModel):
    employee_id: str
    dates: str
    reason: str

# --- ENDPOINTS ---

@app.post("/auto-punch")
async def auto_punch(data: dict, x_api_key: str = Header(None)):
    if x_api_key != "HR_INNOVATE_2026": 
        raise HTTPException(status_code=401)
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO attendance (employee_id, timestamp, action, lat, lon) VALUES (?, ?, ?, ?, ?)",
                   (data.get('employee_id', 'Unknown'), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), data.get('action'), data.get('lat'), data.get('lon')))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/request-leave")
async def request_leave(req: LeaveRequest, x_api_key: str = Header(None)):
    if x_api_key != "HR_INNOVATE_2026": 
        raise HTTPException(status_code=401, detail="Invalid API Key")
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO leaves (employee_id, dates, reason, status) VALUES (?, ?, ?, ?)",
                   (req.employee_id, req.dates, req.reason, 'Pending ⏳'))
    conn.commit()
    conn.close()
    return {"msg": "Request received by Command Center"}

@app.get("/policies")
async def get_policies():
    return {
        "policies": [
            {"title": "HR Code of Conduct 2026"},
            {"title": "Global Remote Work Policy"},
            {"title": "Health & Benefits Package"}
        ]
    }

@app.post("/approve-leave/{leave_id}")
async def approve_leave(leave_id: int, admin: str = Depends(verify_admin)):
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE leaves SET status = 'Approved ✅' WHERE id = ?", (leave_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/logs", status_code=303)

@app.get("/export-payroll")
async def export_payroll(admin: str = Depends(verify_admin)):
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT employee_id, action, timestamp FROM attendance ORDER BY employee_id, timestamp")
    records = cursor.fetchall()
    conn.close()

    hours_worked = defaultdict(float)
    current_entry = {}

    for emp, action, ts_str in records:
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            if action == 'ENTRY':
                current_entry[emp] = ts
            elif action == 'EXIT' and emp in current_entry:
                duration = (ts - current_entry[emp]).total_seconds() / 3600.0 
                hours_worked[emp] += duration
                del current_entry[emp] 
        except Exception:
            continue

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee ID", "Total Hours Worked (Calculated)"])
    for emp, hours in hours_worked.items():
        writer.writerow([emp, round(hours, 2)])
    output.seek(0)
    
    return StreamingResponse(
        output, 
        media_type="text/csv", 
        headers={"Content-Disposition": "attachment; filename=Innovate_HR_Payroll.csv"}
    )

# --- THE PRO DASHBOARD ---
@app.get("/logs", response_class=HTMLResponse)
def view_logs(admin: str = Depends(verify_admin)):
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attendance ORDER BY id DESC LIMIT 15")
    att = cursor.fetchall()
    cursor.execute("SELECT * FROM leaves ORDER BY id DESC")
    lvs = cursor.fetchall()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>HR Command Center</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
        <style>
            /* Custom Webkit Scrollbar */
            ::-webkit-scrollbar { width: 8px; }
            ::-webkit-scrollbar-track { background: #0f172a; }
            ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
            ::-webkit-scrollbar-thumb:hover { background: #06b6d4; }
            
            /* Glassmorphism & Effects */
            .glass-card { background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.05); }
            .neon-glow { text-shadow: 0 0 20px rgba(6, 182, 212, 0.6); }
        </style>
    </head>
    <body class="bg-[#0b1120] text-slate-200 min-h-screen font-sans selection:bg-cyan-500/30 overflow-hidden">
        
        <div class="w-full h-screen px-4 py-4 md:px-8 md:py-6 flex flex-col">
            
            <header class="flex justify-between items-center mb-6 glass-card px-8 py-5 rounded-3xl shadow-2xl shadow-cyan-900/10 flex-shrink-0">
                <div class="flex items-center gap-5">
