import json
import traceback

from fastapi.websockets import WebSocket


class JSONSocket:
    def __init__(self, socket: WebSocket):
        self.socket = socket

    async def __aenter__(self):
        data = await self.socket.receive_text()
        return json.loads(data)


    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if not exc_type:
            await self.socket.send_text('<<<END>>>')
        else:
            print(f'Error: {exc_type}')
            traceback.print_exc()
            await self.socket.send_text('<<<ERROR>>>')