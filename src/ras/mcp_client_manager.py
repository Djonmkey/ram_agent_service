import threading

class MCPClientManager:
    def __init__(self):
        self.clients = {}
        self.lock = threading.Lock()

    def add_client(self, agent_name, client):
        with self.lock:
            self.clients[agent_name] = client

    def get_client(self, agent_name):
        with self.lock:
            return self.clients.get(agent_name)
