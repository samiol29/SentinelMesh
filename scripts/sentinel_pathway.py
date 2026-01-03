import pathway as pw
import docker
import ollama

# 1. THE INPUT CONNECTOR (The Nervous System)
class DockerConnector(pw.io.python.ConnectorSubject):
    def run(self):
        client = docker.from_env()
        print("📡 Sentinel Nervous System: Connected to Docker Stream...")
        for event in client.events(decode=True):
            if event.get("Type") == "container" and event.get("Action") in ["die", "stop", "kill"]:
                self.next( # Updated to use the 'next' method
                    node=event.get("Actor", {}).get("Attributes", {}).get("name"),
                    event=event.get("Action"),
                    severity="HIGH"
                )

# 2. THE OUTPUT OBSERVER (The Brain's Action)
class SentinelGuard(pw.io.python.ConnectorObserver):
    def on_change(self, key, row, time, is_addition):
        # We only care about new additions to the 'Critical' table
        if is_addition:
            node = row['node']
            action = row['event']
            
            print(f"\n[!] Pathway Alert: Node {node} is {action}!")
            
            prompt = f"Security Alert: Node {node} is {action}. Provide a 1-sentence Sentinel protocol action."
            
            response = ollama.chat(model='llama3.2:1b', messages=[
                {'role': 'system', 'content': 'You are the Sentinel-2.0 Autonomous Security Agent.'},
                {'role': 'user', 'content': prompt}
            ])
            
            print(f"🤖 AI REASONING: {response['message']['content']}")

    def on_end(self): pass
    def on_time_end(self, time): pass

# 3. ASSEMBLY
connector = DockerConnector()

# Read the stream
data = pw.io.python.read(
    connector,
    schema=pw.schema_from_dict({"node": str, "event": str, "severity": str})
)

# 4. EXECUTION
# We pass the class instance to the write function
pw.io.python.write(data, SentinelGuard())

if __name__ == "__main__":
    pw.run()
