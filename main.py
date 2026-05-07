from fastapi import FastAPI, HTTPException, Header, Depends, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
import sqlite3, secrets
from datetime import datetime
import csv
from io import StringIO
from collections import defaultdict
import urllib.request
import json

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
    # NEW: Table to store device push tokens
    cursor.execute('CREATE TABLE IF NOT EXISTS users (employee_id TEXT PRIMARY KEY, push_token TEXT)')
    conn.commit()
    conn.close()

init_db()

# --- PYDANTIC MODELS ---
class LeaveRequest(BaseModel):
    employee_id: str
    dates: str
    reason: str

class DeviceToken(BaseModel):
    employee_id: str
    push_token: str

# --- EXPO PUSH NOTIFICATION ENGINE ---
def send_push_notification(token, title, body):
    url = "https://exp.host/--/api/v2/push/send"
    payload = {"to": token, "title": title, "body": body, "sound": "default"}
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
    except Exception as e:
        print("Push failed:", e)

# --- ENDPOINTS ---
@app.post("/register-device")
async def register_device(data: DeviceToken, x_api_key: str = Header(None)):
    if x_api_key != "HR_INNOVATE_2026": raise HTTPException(status_code=401)
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (employee_id, push_token) VALUES (?, ?)", (data.employee_id, data.push_token))
    conn.commit()
    conn.close()
    return {"status": "Device registered"}

@app.post("/auto-punch")
async def auto_punch(data: dict, x_api_key: str = Header(None)):
    if x_api_key != "HR_INNOVATE_2026": raise HTTPException(status_code=401)
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO attendance (employee_id, timestamp, action, lat, lon) VALUES (?, ?, ?, ?, ?)",
                   (data.get('employee_id', 'Unknown'), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), data.get('action'), data.get('lat'), data.get('lon')))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/request-leave")
async def request_leave(req: LeaveRequest, x_api_key: str = Header(None)):
    if x_api_key != "HR_INNOVATE_2026": raise HTTPException(status_code=401)
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
        "policies": [{"title": "HR Code of Conduct 2026"}, {"title": "Global Remote Work Policy"}, {"title": "Health & Benefits Package"}]
    }

@app.post("/approve-leave/{leave_id}")
async def approve_leave(leave_id: int, admin: str = Depends(verify_admin)):
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    
    # 1. Find who requested this leave
    cursor.execute("SELECT employee_id FROM leaves WHERE id = ?", (leave_id,))
    emp = cursor.fetchone()
    
    # 2. Update the status
    cursor.execute("UPDATE leaves SET status = 'Approved ✅' WHERE id = ?", (leave_id,))
    
    # 3. Fetch their token and send the push notification
    if emp:
        emp_id = emp[0]
        cursor.execute("SELECT push_token FROM users WHERE employee_id = ?", (emp_id,))
        token_row = cursor.fetchone()
        if token_row and token_row[0]:
            send_push_notification(token_row[0], "Leave Approved! 🎉", f"Your time off request has been authorized by HR.")
            
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
            if action == 'ENTRY': current_entry[emp] = ts
            elif action == 'EXIT' and emp in current_entry:
                duration = (ts - current_entry[emp]).total_seconds() / 3600.0 
                hours_worked[emp] += duration
                del current_entry[emp] 
        except Exception: continue

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Employee ID", "Total Hours Worked (Calculated)"])
    for emp, hours in hours_worked.items(): writer.writerow([emp, round(hours, 2)])
    output.seek(0)
    
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=Innovate_HR_Payroll.csv"})

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
            ::-webkit-scrollbar { width: 8px; }
            ::-webkit-scrollbar-track { background: #0f172a; }
            ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
            ::-webkit-scrollbar-thumb:hover { background: #06b6d4; }
            .glass-card { background: rgba(15, 23, 42, 0.7); backdrop-filter: blur(16px); border: 1px solid rgba(255, 255, 255, 0.05); }
            .neon-glow { text-shadow: 0 0 20px rgba(6, 182, 212, 0.6); }
        </style>
    </head>
    <body class="bg-[#0b1120] text-slate-200 min-h-screen font-sans selection:bg-cyan-500/30 overflow-hidden">
        
        <div class="w-full h-screen px-4 py-4 md:px-8 md:py-6 flex flex-col">
            <header class="flex justify-between items-center mb-6 glass-card px-8 py-5 rounded-3xl shadow-2xl shadow-cyan-900/10 flex-shrink-0">
                <div class="flex items-center gap-5">
                    <div class="h-14 w-14 rounded-full bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center shadow-[0_0_20px_rgba(6,182,212,0.4)] animate-pulse">
                        <span class="text-white font-black text-xl tracking-tighter">HR</span>
                    </div>
                    <div>
                        <h1 class="text-3xl font-black bg-gradient-to-r from-cyan-400 via-blue-400 to-indigo-400 bg-clip-text text-transparent neon-glow tracking-tight leading-tight">COMMAND CENTER</h1>
                        <p class="text-cyan-500/80 text-sm font-bold tracking-widest uppercase">Global Tracking Network</p>
                    </div>
                </div>
                
                <div class="flex items-center gap-6">
                    <a href="/export-payroll" class="group relative px-6 py-3 font-bold text-slate-900 rounded-xl bg-gradient-to-r from-emerald-400 to-emerald-500 overflow-hidden shadow-[0_0_20px_rgba(52,211,153,0.3)] hover:shadow-[0_0_30px_rgba(52,211,153,0.6)] transition-all transform hover:-translate-y-1">
                        <span class="relative z-10 flex items-center gap-2">📥 EXPORT PAYROLL</span>
                        <div class="absolute inset-0 h-full w-full bg-white/20 group-hover:scale-110 transition-transform"></div>
                    </a>
                    <div class="bg-slate-900/80 px-5 py-3 rounded-xl border border-slate-700/50 text-sm font-bold flex items-center gap-3">
                        <span class="relative flex h-3 w-3"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span><span class="relative inline-flex rounded-full h-3 w-3 bg-cyan-500"></span></span>
                        Admin Mode
                    </div>
                </div>
            </header>

            <div class="grid grid-cols-1 xl:grid-cols-4 gap-6 flex-grow min-h-0">
                <div class="xl:col-span-1 glass-card p-6 rounded-3xl flex flex-col h-full shadow-2xl">
                    <h2 class="text-xl font-black mb-6 flex items-center gap-3 text-white border-b border-slate-700/50 pb-4"><span class="text-2xl">📅</span> Action Queue</h2>
                    <div class="space-y-4 overflow-y-auto pr-2 flex-grow">
    """
    
    for l in lvs:
        status_color = "text-emerald-400" if "Approved" in l[4] else "text-amber-400"
        html += f"""
                        <div class="p-5 bg-slate-800/40 hover:bg-slate-800/80 rounded-2xl border border-slate-700/50 transition-all duration-300 group shadow-lg">
                            <div class="flex justify-between items-start mb-3">
                                <p class="font-bold text-white text-lg group-hover:text-cyan-400 transition-colors">{l[1]}</p>
                                <span class="text-xs font-bold px-3 py-1 rounded-md bg-slate-900 {status_color} border border-slate-700">{l[4]}</span>
                            </div>
                            <p class="text-sm text-slate-300 font-medium bg-slate-900/50 p-3 rounded-xl border border-slate-800 mb-4">{l[2]}</p>
                            {f'<form action="/approve-leave/{l[0]}" method="post"><button class="w-full py-3 bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 rounded-xl text-sm font-black text-white shadow-[0_0_15px_rgba(6,182,212,0.3)] transition-all hover:scale-[1.02]">AUTHORIZE LEAVE</button></form>' if 'Pending' in l[4] else ''}
                        </div>
        """
    
    html += """
                    </div>
                </div>

                <div class="xl:col-span-3 flex flex-col gap-6 h-full">
                    <div class="relative h-3/5 rounded-3xl overflow-hidden glass-card border border-slate-700/50 shadow-[0_0_40px_rgba(0,0,0,0.5)]">
                        <div class="absolute top-5 left-5 z-[400] bg-slate-900/90 backdrop-blur px-5 py-2 rounded-xl border border-slate-700 text-sm font-black text-cyan-400 shadow-lg flex items-center gap-2">
                            <div class="h-2 w-2 bg-cyan-400 rounded-full animate-pulse"></div> Live Tracking Active
                        </div>
                        <div id="map" class="h-full w-full"></div>
                    </div>

                    <div class="h-2/5 glass-card p-1 rounded-3xl overflow-hidden flex flex-col border border-slate-700/50">
                        <div class="overflow-y-auto w-full h-full rounded-2xl">
                            <table class="w-full text-left text-sm border-collapse relative">
                                <thead class="sticky top-0 bg-[#0f172a] z-10 shadow-md">
                                    <tr class="text-slate-400 uppercase tracking-widest text-[10px] font-bold">
                                        <th class="py-5 px-6">Employee ID</th>
                                        <th class="py-5 px-6">Event Type</th>
                                        <th class="py-5 px-6 text-right">GPS Coordinates</th>
                                    </tr>
                                </thead>
                                <tbody class="divide-y divide-slate-800/50 bg-slate-900/20">
    """
    
    for r in att:
        color = "text-emerald-400 bg-emerald-400/10 border-emerald-400/30" if r[3] == "ENTRY" else "text-rose-400 bg-rose-400/10 border-rose-400/30"
        html += f"""
                                    <tr class="hover:bg-slate-800/60 transition-colors group">
                                        <td class="py-4 px-6 font-bold text-white text-base group-hover:text-cyan-400 transition-colors flex items-center gap-3">
                                            <div class="h-8 w-8 rounded-full bg-slate-800 flex items-center justify-center text-xs text-slate-400">{r[1][0] if r[1] else '?'}</div>
                                            {r[1]}
                                        </td>
                                        <td class="py-4 px-6"><span class="px-4 py-1.5 rounded-lg font-black text-xs border {color} shadow-sm">{r[3]}</span></td>
                                        <td class="py-4 px-6 text-slate-500 font-mono text-right text-xs bg-slate-900/30 group-hover:text-slate-300 transition-colors rounded-l-xl">{r[4]}<br/><span class="opacity-50">{r[5]}</span></td>
                                    </tr>
        """
    
    html += """
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            var map = L.map('map', { zoomControl: false }).setView([43.7, -79.3], 3);
            L.control.zoom({ position: 'bottomright' }).addTo(map);

            L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', { attribution: '&copy; OpenStreetMap', subdomains: 'abcd', maxZoom: 20 }).addTo(map);

            var neonIcon = L.divIcon({ className: 'custom-div-icon', html: '<div style="background-color: #06b6d4; width: 14px; height: 14px; border-radius: 50%; border: 2px solid #fff; box-shadow: 0 0 15px #06b6d4, 0 0 30px #06b6d4; animation: pulse 2s infinite;"></div>', iconSize: [14, 14], iconAnchor: [7, 7] });
    """
    
    for r in att:
        html += f"L.marker([{r[4]}, {r[5]}], {{icon: neonIcon}}).addTo(map).bindPopup('<div style=\"text-align:center;\"><b style=\"color:#0f172a; font-size:14px;\">{r[1]}</b><br/><span style=\"color:#64748b; font-size:10px; font-weight:bold;\">{r[3]}</span></div>');"
    
    html += """
        </script>
    </body>
    </html>
    """
    return html