from fastapi import FastAPI, HTTPException, Header, Depends, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
import sqlite3, secrets, math
from datetime import datetime

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

# --- ENDPOINTS ---
@app.post("/auto-punch")
async def auto_punch(data: dict, x_api_key: str = Header(None)):
    if x_api_key != "HR_INNOVATE_2026": raise HTTPException(status_code=401)
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO attendance (employee_id, timestamp, action, lat, lon) VALUES (?, ?, ?, ?, ?)",
                   (data['employee_id'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), data['action'], data['lat'], data['lon']))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/approve-leave/{leave_id}")
async def approve_leave(leave_id: int, admin: str = Depends(verify_admin)):
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE leaves SET status = 'Approved ✅' WHERE id = ?", (leave_id,))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/logs", status_code=303)

# --- THE PRO DASHBOARD ---
@app.get("/logs", response_class=HTMLResponse)
def view_logs(admin: str = Depends(verify_admin)):
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attendance ORDER BY id DESC LIMIT 10")
    att = cursor.fetchall()
    cursor.execute("SELECT * FROM leaves ORDER BY id DESC")
    lvs = cursor.fetchall()
    conn.close()

    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
        <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    </head>
    <body class="bg-slate-950 text-slate-200 p-8">
        <div class="max-w-7xl mx-auto">
            <header class="flex justify-between mb-10">
                <h1 class="text-3xl font-black bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">HR COMMAND CENTER PRO</h1>
                <div class="bg-slate-800 px-4 py-2 rounded-lg border border-slate-700 text-sm">Admin: Global Mode</div>
            </header>

            <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
                <div class="lg:col-span-1 bg-slate-900 border border-slate-800 p-6 rounded-3xl">
                    <h2 class="text-xl font-bold mb-6">📅 Leave Approvals</h2>
                    <div class="space-y-4">
    """
    for l in lvs:
        html += f"""
                        <div class="p-4 bg-slate-800 rounded-2xl border border-slate-700">
                            <p class="font-bold text-white">{l[1]} <span class="text-xs font-normal text-slate-400">{l[4]}</span></p>
                            <p class="text-sm text-cyan-400 my-1">{l[2]}</p>
                            {f'<form action="/approve-leave/{l[0]}" method="post"><button class="mt-2 w-full py-2 bg-cyan-600 hover:bg-cyan-500 rounded-xl text-xs font-bold transition">APPROVE REQUEST</button></form>' if 'Pending' in l[4] else ''}
                        </div>
        """
    
    html += """
                    </div>
                </div>

                <div class="lg:col-span-2 space-y-8">
                    <div id="map" class="h-80 rounded-3xl border border-slate-800 shadow-2xl"></div>
                    <div class="bg-slate-900 border border-slate-800 p-6 rounded-3xl">
                        <h2 class="text-xl font-bold mb-6 text-white">📡 Global Access Logs</h2>
                        <table class="w-full text-left text-sm">
                            <tr class="text-slate-500 border-b border-slate-800"><th class="pb-3">Employee</th><th class="pb-3">Action</th><th class="pb-3">Coordinates</th></tr>
    """
    for r in att:
        color = "text-emerald-400" if r[3] == "ENTRY" else "text-rose-400"
        html += f"<tr><td class='py-3 font-medium text-white'>{r[1]}</td><td class='{color} font-bold'>{r[3]}</td><td class='text-slate-500'>{r[4]}, {r[5]}</td></tr>"
    
    html += """
                        </table>
                    </div>
                </div>
            </div>
        </div>
        <script>
            var map = L.map('map').setView([20, 0], 2);
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '© OSM' }).addTo(map);
    """
    for r in att:
        html += f"L.marker([{r[4]}, {r[5]}]).addTo(map).bindPopup('{r[1]}: {r[3]}');"
    
    html += """
        </script>
    </body>
    </html>
    """
    return html
