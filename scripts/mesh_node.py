import socket
import time
import os

# Port for internal mesh communication
PORT = 9999
NODE_NAME = os.getenv("HOSTNAME", "unknown-node")

def start_sensor():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', PORT))
    server.listen(5)
    print(f"📡 {NODE_NAME} RL-Sensor active on port {PORT}...")

    while True:
        try:
            conn, addr = server.accept()
            data = conn.recv(1024).decode()
            if data == "PING":
                # Respond with timestamp to calculate latency
                conn.send(f"PONG|{time.time()}".encode())
            conn.close()
        except Exception as e:
            print(f"Sensor Error: {e}")

if __name__ == "__main__":
    start_sensor()
