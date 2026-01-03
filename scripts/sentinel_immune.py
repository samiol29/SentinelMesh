import docker
import ollama
import asyncio
import threading
import time
import json
import os
import socket
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import http.client

# --- PHASE 5: RL ROUTING CONFIG ---
q_table = {}
MEMORY_FILE = "sentinel_memory.json"
alert_queue = asyncio.Queue()
active_connections = []
node_states = {}
loop = None 

SAFE_COMMANDS = {
    "check_load": "uptime",
    "check_network": "ip addr show",
    "clear_logs": "truncate -s 0 /var/log/*.log",
    "check_processes": "ps aux",
    "verify_storage": "df -h"
}

def update_rl_score(node_name, latency, success):
    current_q = q_table.get(node_name, 20.0) # Start at 20% to see movement
    alpha = 0.3 # High learning rate for the demo
    
    if success:
        reward = 50  # Massive boost for successful pings
    else:
        reward = -20 # Smaller penalty so one failure doesn't kill the score
        
    new_q = current_q + alpha * (reward - current_q)
    q_table[node_name] = max(0, min(100, round(new_q, 2)))

# Map your node names to their LOCALHOST ports
NODE_PORT_MAP = {
    "clab-sentinel-mesh-b-node1": 9001,
    "clab-sentinel-mesh-b-node2": 9002,
    "clab-sentinel-mesh-a-node1": 9003,
    "clab-sentinel-mesh-a-node2": 9004,
    "clab-sentinel-mesh-sentinel-vault": 9005,
    "clab-sentinel-mesh-sentinel-guard": 9006
}

def rl_pinger():
    """Web-based Pinger: Checks if the Node's mini-webserver is alive"""
    while True:
        client = docker.from_env()
        for container in client.containers.list():
            if "sentinel" in container.name and container.status == "running":
                ip = container.attrs['NetworkSettings']['IPAddress']
                start = time.time()
                try:
                    # We use a simple HTTP GET to check health
                    conn = http.client.HTTPConnection(ip, 9999, timeout=0.2)
                    conn.request("GET", "/")
                    resp = conn.getresponse()
                    if resp.status == 200:
                        latency = time.time() - start
                        update_rl_score(container.name, latency, True)
                    conn.close()
                except:
                    update_rl_score(container.name, 0, False)
        time.sleep(2)

# --- AI IMMUNE RESPONSE ---
def trigger_immune_response(node, status):
    client = docker.from_env()
    count = load_memory().get(node, {}).get("occurrence_count", 0) + 1
    
    # FORCED JSON PROMPT: Best for 1B models to prevent 'Blocked' vaccines
    system_instruction = (
        "You are a Sentinel Core. Respond ONLY in this format: "
        "REASONING | ID. Example: High load detected | check_load. "
        "Valid IDs: ['check_load', 'check_network', 'clear_logs', 'check_processes', 'verify_storage']"
    )
    
    try:
        res = ollama.chat(model='llama3.2:1b', messages=[
            {'role': 'system', 'content': system_instruction},
            {'role': 'user', 'content': f"NODE: {node} STATUS: {status}"}
        ])
        raw = res['message']['content']
        
        # Smart Parsing
        key_requested = "check_load" # Default
        for k in SAFE_COMMANDS.keys():
            if k in raw.lower():
                key_requested = k
                break
        
        actual_cmd = SAFE_COMMANDS[key_requested]
        display_explanation = f"RL Recovery initiated: {key_requested} deployed to restore mesh integrity."
        
        # Execute on others
        for c in client.containers.list():
            if "sentinel" in c.name and c.name != node:
                try: c.exec_run(actual_cmd, detach=True)
                except: pass

        # Broadcast to UI
        card_html = format_card(node, display_explanation, actual_cmd, "VACCINE DEPLOYED", "border-indigo-500", count)
        asyncio.run_coroutine_threadsafe(alert_queue.put(card_html), loop)
    except: pass

def format_card(node, explanation, cmd, status, border, count):
    score = q_table.get(node, 0)
    return f"""
    <div class="p-4 bg-gray-900 border-l-4 {border} rounded-lg mb-4">
        <div class="flex justify-between items-center mb-2">
            <span class="text-[10px] font-bold text-indigo-400 uppercase">Resolution #{count}</span>
            <span class="text-[10px] font-mono text-white">Reliability at event: {score}%</span>
        </div>
        <h3 class="text-white font-bold text-sm">{node}</h3>
        <p class="text-gray-400 text-xs italic">"{explanation}"</p>
        <div class="mt-2 text-[10px] font-mono text-indigo-500">CMD: {cmd} | STATUS: {status}</div>
    </div>
    """

def load_memory():
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, 'r') as f: return json.load(f)
    return {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    threading.Thread(target=rl_pinger, daemon=True).start()
    threading.Thread(target=lambda: docker_watcher(loop), daemon=True).start()
    yield

def docker_watcher(main_loop):
    client = docker.from_env()
    while True:
        try:
            for c in client.containers.list(all=True):
                if "sentinel" in c.name:
                    c.reload()
                    # If node is down OR if score is 0 but node is running (Sensor is dead)
                    if (c.status != "running") or (c.status == "running" and q_table.get(c.name, 100) < 1):
                        
                        if c.status != "running":
                            print(f"🔄 Restarting {c.name}...")
                            c.start()
                            time.sleep(2) # Give it a moment to boot
                        
                        # FORCE SENSOR START: Use a more robust 'while' loop for the sensor
                        # We use 'sh -c' to ensure the background process detaches properly
                        sensor_cmd = 'sh -c "while true; do { echo -e \'HTTP/1.1 200 OK\\n\\nPONG\'; } | nc -lp 9999; done"'
                        c.exec_run(sensor_cmd, detach=True)
                        
                        # Only trigger the AI if it was an actual crash
                        if node_states.get(c.name) == "running" and c.status != "running":
                            trigger_immune_response(c.name, c.status)
                    
                    node_states[c.name] = c.status
        except Exception as e:
            print(f"Watcher Error: {e}")
        time.sleep(2)

app = FastAPI(lifespan=lifespan)
@app.get("/")
async def get(): return HTMLResponse(open("dashboard.html").read())
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            await websocket.send_json({"type": "stats", "scores": q_table})
            while not alert_queue.empty():
                msg = await alert_queue.get()
                await websocket.send_json({"type": "resolution", "html": msg})
            await asyncio.sleep(1)
    except: active_connections.remove(websocket)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
