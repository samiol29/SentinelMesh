import docker, ollama, asyncio, threading, time, socket
from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

# --- CONFIG & STATE ---
PORT_MAP = {
    "clab-sentinel-mesh-a-node1": 9001, "clab-sentinel-mesh-a-node2": 9002,
    "clab-sentinel-mesh-b-node1": 9003, "clab-sentinel-mesh-b-node2": 9004
}
q_table = {name: {"score": 50.0, "latency": 0} for name in PORT_MAP.keys()}
OVERRIDE_ROUTE = None 
alert_queue = asyncio.Queue()
loop = None 

def get_best_route():
    if OVERRIDE_ROUTE: return f"MANUAL: {OVERRIDE_ROUTE}"
    a_avg = sum(q_table[n]["score"] for n in q_table if "-a-" in n) / 2
    b_avg = sum(q_table[n]["score"] for n in q_table if "-b-" in n) / 2
    return "AUTO: SUBNET-A" if a_avg >= b_avg else "AUTO: SUBNET-B"

# --- REASONING ENGINE (Restored Deep Analysis) ---
def trigger_immune_response(node, condition):
    # Detailed system role to get the multi-line analysis back
    system_role = (
        "You are SENTINEL-CORE. Analyze node failures by cross-referencing peers. "
        "Format: [REASON] | [PEER_STATUS] | [ACTION]. Be technical and dense."
    )
    prompt = f"ALARM: Node {node} reports {condition}. Status of other nodes: {q_table}. Analyze subnet correlation."

    try:
        res = ollama.chat(model='llama3.2:1b', messages=[
            {'role': 'system', 'content': system_role}, {'role': 'user', 'content': prompt}
        ], options={'temperature': 0.3}) # Slightly higher temp for better descriptions
        asyncio.run_coroutine_threadsafe(alert_queue.put(res['message']['content']), loop)
    except: pass

def update_rl_score(node_name, success, latency):
    current = q_table.get(node_name, {"score": 50.0, "latency": 0})
    # Strict thresholds: <50ms = Green, 50-150ms = Warning, >150ms = Critical
    reward = 100 if (success and latency < 50) else (40 if (success and latency < 150) else 0)
    alpha = 0.5
    new_score = current["score"] + alpha * (reward - current["score"])
    q_table[node_name] = {"score": round(max(0, min(100, new_score)), 2), "latency": round(latency, 1)}

# --- SYSTEM THREADS ---
def rl_pinger():
    while True:
        for node_name, port in PORT_MAP.items():
            start = time.time()
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2) as sock:
                    sock.sendall(b"PING")
                    if b"PONG" in sock.recv(1024):
                        lat = (time.time() - start) * 1000
                        update_rl_score(node_name, True, lat)
                    else: update_rl_score(node_name, False, 0)
            except: update_rl_score(node_name, False, 0)
        time.sleep(1)

def docker_watcher():
    client = docker.from_env()
    while True:
        for node_name in PORT_MAP.keys():
            if q_table[node_name]["score"] < 25.0:
                try:
                    c = client.containers.get(node_name)
                    if c.status != "running":
                        c.start()
                        time.sleep(2)
                        c.exec_run("python3 /mesh_sensor.py", detach=True)
                        trigger_immune_response(node_name, "CRITICAL_LATENCY_FAILURE")
                except: pass
        time.sleep(2)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global loop
    loop = asyncio.get_running_loop()
    threading.Thread(target=rl_pinger, daemon=True).start()
    threading.Thread(target=docker_watcher, daemon=True).start()
    yield

app = FastAPI(lifespan=lifespan)
@app.get("/")
async def get(): return HTMLResponse(open("dashboard.html").read())

@app.post("/override/{route}")
async def set_override(route: str):
    global OVERRIDE_ROUTE
    OVERRIDE_ROUTE = None if route.lower() == "clear" else f"SUBNET-{route.upper()}"
    await alert_queue.put(f"OPERATOR_OVERRIDE: {OVERRIDE_ROUTE}" if OVERRIDE_ROUTE else "AUTONOMY RESTORED")
    return {"status": "success"}

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await websocket.send_json({"type": "stats", "scores": q_table, "route": get_best_route()})
            while not alert_queue.empty():
                msg = await alert_queue.get()
                await websocket.send_json({"type": "resolution", "html": msg})
            await asyncio.sleep(0.3)
    except: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
