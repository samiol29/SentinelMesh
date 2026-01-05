import socket
import os

def run_sensor():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', 9999))
        s.listen()
        print(f"Intelligence Sensor Active on port 9999")
        while True:
            conn, addr = s.accept()
            with conn:
                data = conn.recv(1024)
                if b"PING" in data:
                    conn.sendall(b"PONG")

if __name__ == "__main__":
    run_sensor()
