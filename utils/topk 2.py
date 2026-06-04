import heapq
from typing import Any


class TopK:
    def __init__(self, k: int) -> None:
        self.k = k
        self.heap = []

    def insert(self, value: float, data: Any) -> None:
        item = (value, id(data), data)
        if len(self.heap) < self.k:
            heapq.heappush(self.heap, item)
        else:
            
            if value > self.heap[0][0]:
                heapq.heappushpop(self.heap, item)

    def get_topk(self) -> list[tuple[float, Any]]:
        
        return [(item[0], item[2]) for item in sorted(self.heap, key=lambda x: -x[0])]
