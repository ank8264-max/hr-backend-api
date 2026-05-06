from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from math import radians, cos, sin, asin, sqrt
import sqlite3
from datetime import datetime
import secrets

app = FastAPI()
security = HTTPBasic()

# --- 1. ADMIN SECURITY LOGIC ---
def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    # YOUR ADMIN CREDENTIALS
    correct_username = secrets.compare_digest(credentials.username, "admin")
    correct_password = secrets.compare_digest(credentials.password, "Innovate2026!")
    
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect Username or Password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# --- 2. DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS attendance (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT, timestamp TEXT, action TEXT, distance REAL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS leaves (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id TEXT, dates TEXT, reason TEXT, status TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS policies (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, link TEXT)''')
    
    cursor.execute("SELECT COUNT(*) FROM policies")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO policies (title, link) VALUES ('2026 Health Benefits', 'https://example.com/health.pdf')")
        cursor.execute("INSERT INTO policies (title, link) VALUES ('Company Code of Conduct', 'https://example.com/conduct.pdf')")
    conn.commit()
    conn.close()

init_db()

# --- 3. CONFIGURATION ---
OFFICE_LAT, OFFICE_LON = 43.7941, -79.3512 
GEOFENCE_RADIUS = 500000 
SECRET_API_KEY = "HR_INNOVATE_2026"

def get_distance(lat1, lon1, lat2, lon2):
    R = 6371000 
    dlon, dlat = radians(lon2 - lon1), radians(lat2 - lat1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * (2 * asin(sqrt(a)))

class PunchRequest(BaseModel):
    employee_id: str
    lat: float
    lon: float
    action: str

class LeaveRequest(BaseModel):
    employee_id: str
    dates: str
    reason: str

# --- 4. API ENDPOINTS ---
@app.post("/auto-punch")
async def auto_punch(data: PunchRequest, x_api_key: str = Header(None)):
    if x_api_key != SECRET_API_KEY: raise HTTPException(status_code=401)
    distance = get_distance(data.lat, data.lon, OFFICE_LAT, OFFICE_LON)
    if data.action == "ENTRY" and distance > GEOFENCE_RADIUS:
        return {"status": "fail", "msg": "Too far away to punch in."}

    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT INTO attendance (employee_id, timestamp, action, distance) VALUES (?, ?, ?, ?)",
                   (data.employee_id, now, data.action, round(distance, 2)))
    conn.commit()
    conn.close()
    return {"status": "success", "msg": f"Successfully logged {data.action}."}

@app.post("/request-leave")
async def request_leave(data: LeaveRequest, x_api_key: str = Header(None)):
    if x_api_key != SECRET_API_KEY: raise HTTPException(status_code=401)
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT INTO leaves (employee_id, dates, reason, status) VALUES (?, ?, ?, ?)", (data.employee_id, data.dates, data.reason, 'Pending'))
    conn.commit()
    conn.close()
    return {"status": "success", "msg": "Leave request submitted."}

@app.get("/policies")
async def get_policies():
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT title, link FROM policies")
    records = cursor.fetchall()
    conn.close()
    return {"policies": [{"title": r[0], "link": r[1]} for r in records]}

# --- 5. SECURE COMMAND CENTER UI ---
# Notice the 'admin: str = Depends(verify_admin)' below. This locks the page!
@app.get("/logs", response_class=HTMLResponse)
def view_logs(admin: str = Depends(verify_admin)):
    conn = sqlite3.connect('hr_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM attendance ORDER BY timestamp DESC LIMIT 8")
    att = cursor.fetchall()
    cursor.execute("SELECT * FROM leaves ORDER BY id DESC LIMIT 4")
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
    </head>
    <body class="bg-slate-900 text-slate-200 font-sans p-8">
        <div class="max-w-6xl mx-auto">
            <div class="flex justify-between items-center mb-8">
                <h1 class="text-4xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">Ankush's HR Command Center</h1>
                <span class="px-4 py-2 bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 rounded-full font-bold text-sm">🔒 Admin: """ + admin + """</span>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                <div class="bg-slate-800 p-6 rounded-2xl shadow-xl border border-slate-700">
                    <h2 class="text-2xl font-bold text-white mb-6 flex items-center">📡 Live Sensor Feed</h2>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left border-collapse">
                            <thead>
                                <tr class="text-slate-400 border-b border-slate-700">
                                    <th class="pb-3 font-medium">Employee</th>
                                    <th class="pb-3 font-medium">Time</th>
                                    <th class="pb-3 font-medium">Action</th>
                                </tr>
                            </thead>
                            <tbody>
    """
    for r in att: 
        badge_color = "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" if r[3] == "ENTRY" else "bg-rose-500/20 text-rose-400 border-rose-500/30"
        html += f"""
                                <tr class="border-b border-slate-700/50 hover:bg-slate-700/25 transition">
                                    <td class="py-4 font-semibold text-white">{r[1]}</td>
                                    <td class="py-4 text-slate-300 text-sm">{r[2]}</td>
                                    <td class="py-4"><span class="px-3 py-1 rounded-full text-xs font-bold border {badge_color}">{r[3]}</span></td>
                                </tr>
        """
    html += """
                            </tbody>
                        </table>
                    </div>
                </div>

                <div class="bg-slate-800 p-6 rounded-2xl shadow-xl border border-slate-700">
                    <h2 class="text-2xl font-bold text-white mb-6 flex items-center">📅 Pending Time Off</h2>
                    <div class="space-y-4">
    """
    for l in lvs:
        html += f"""
                        <div class="bg-slate-900 p-4 rounded-xl border border-slate-700 flex justify-between items-center">
                            <div>
                                <p class="text-white font-bold">{l[1]} <span class="text-slate-400 font-normal text-sm ml-2">({l[3]})</span></p>
                                <p class="text-emerald-400 text-sm mt-1">{l[2]}</p>
                            </div>
                            <span class="px-3 py-1 bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-full text-xs font-bold">Review</span>
                        </div>
        """
    html += """
                    </div>
                </div>
            </div>
        </div>
    </body>
    </html>
    """
    return html
