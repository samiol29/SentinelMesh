import docker
import ollama

# Initialize the Docker client
client = docker.from_env()

def restart_node(node_name: str) -> str:
    """
    Restarts a specific Docker container by its name.
    Args:
        node_name: The exact name of the container to restart.
    Returns:
        A message indicating success or failure.
    """
    try:
        print(f"🔧 Action: AI is attempting to restart {node_name}...")
        container = client.containers.get(node_name)
        container.restart()
        return f"SUCCESS: {node_name} has been brought back online."
    except Exception as e:
        return f"FAILED: Error restarting {node_name}: {str(e)}"

def get_network_status():
    """Fetches the current state of all nodes in the sentinel mesh."""
    # We use all=True to find containers that are stopped/exited
    containers = client.containers.list(all=True, filters={"name": "clab-sentinel-mesh"})
    
    if not containers:
        return "No nodes found in the sentinel-mesh project."
    
    status_list = []
    for c in containers:
        status_list.append(f"Node: {c.name} | State: {c.status}")
    
    return "\n".join(status_list)

def main():
    # 1. Capture current network state
    current_state = get_network_status()
    print(f"--- Sentinel Observation ---\n{current_state}\n")

    # 2. Define the instructions for the AI
    system_prompt = (
        "You are the Sentinel Mesh Autonomous Controller. "
        "Your goal is to ensure all mesh nodes are in the 'running' state. "
        "If any node is in 'exited' or 'created' state, you MUST call the restart_node tool. "
        "If all nodes are 'running', provide a brief health summary."
    )

    # 3. Chat with the AI using Tool Support
    # We use llama3.2:1b because it's fast and supports tool calling natively
    response = ollama.chat(
        model='llama3.2:1b',
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': f"Current Network State:\n{current_state}"}
        ],
        tools=[restart_node], # This passes the function signature to the AI
    )

    # 4. Handle Tool Calls (The "Acting" phase)
    if response.message.tool_calls:
        print("💡 AI Decision: Intervention required.")
        for tool in response.message.tool_calls:
            if tool.function.name == 'restart_node':
                # Execute the function with arguments provided by AI
                result = restart_node(**tool.function.arguments)
                print(f"Result: {result}")
        
        # After fixing, the AI can give a final confirmation
        final_response = ollama.chat(
            model='llama3.2:1b',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': f"Action performed. Current state: All nodes restarting."},
            ]
        )
        print(f"\nAI Final Report: {final_response.message.content}")
    else:
        # If no tools were called, just print the AI's analysis
        print("--- Sentinel AI Health Report ---")
        print(response.message.content)

if __name__ == "__main__":
    main()
