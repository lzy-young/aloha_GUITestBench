

import asyncio
import inspect
import queue
import re
import threading
import time
from typing import Union, AsyncGenerator, Generator, Optional

from fastapi.responses import StreamingResponse

from utils.fileio import save


class ResponseManager:
    def __init__(self, interval: float = 1):
        self.interval = interval
        self.full_response = ''
        self.cache = ''
        self.stat = {
            "first_token": '',
            "last_token": '',
            "chunks": 0,
            "blocks": [
                {"tag": 'text', "len": 0}
            ],
        }
        self.ready_contents: list[str] = []

        self.block_tag = None

        self._last_parse_time = 0

        self.start_tag_pattern = re.compile(r'<([a-zA-Z][a-zA-Z0-9_\-:]*)>')

    def delta(self, chunk: str) -> None:
        if self.stat['first_token'] == '':
            self.stat['first_token'] = time.strftime("%Y%m%d-%H%M%S")
        self.stat['last_token'] = time.strftime("%Y%m%d-%H%M%S")

        self.cache += chunk
        if time.time() - self._last_parse_time >= self.interval:
            self.process_cache()
            self._last_parse_time = time.time()

    def flush(self) -> None:
        self.process_cache(preserve_unclosed_tag=False)
        self._last_parse_time = time.time()

    def ready_cache(self, l: int, block_stat: bool = True):
        if l == 0:
            return
        c = self.cache[:l]
        self.cache = self.cache[l:]
        self.full_response += c
        self.ready_contents.append(c)
        self.stat['chunks'] += 1
        if block_stat:
            self.stat['blocks'][-1]["len"] += len(c)

    def search_block_tag(self, target_tag_type: str) -> tuple[int, Optional[str]]:
        if target_tag_type == 'start':
            res = self.start_tag_pattern.search(self.cache)
            if res is None:
                return -1, None
            return res.start(), res.groups()[0]
        else:
            res = self.cache.find(f'</{self.block_tag}>')
            if res == -1:
                return -1, None
            return res, self.block_tag

    def search_possible_block_tag(self, target_tag_type: str) -> tuple[int, Optional[str]]:
        last_idx = self.cache.rfind('<')
        if last_idx == -1:
            return -1, None
        if target_tag_type == 'start':
            tag = self.cache[last_idx + 1:]
            pattern = re.compile(r'^([a-zA-Z][a-zA-Z0-9_\-:]*)?$')
            if pattern.match(tag):
                return last_idx, self.cache[last_idx + 1:]
            else:
                return -1, None
        else:
            if f'</{self.block_tag}>'.startswith(self.cache[last_idx:]):
                return last_idx, self.cache[last_idx + 2:]
            else:
                return -1, None

    def process_cache(self, preserve_unclosed_tag: bool = True) -> None:
        target_tag_type = 'start' if self.block_tag is None else 'end'
        idx, block_tag = self.search_block_tag(target_tag_type)
        
        if block_tag is not None:
            self.block_tag = block_tag if target_tag_type == 'start' else None
            self.ready_cache(idx)
            self.stat['blocks'].append({'tag': 'text' if self.block_tag is None else self.block_tag, 'len': 0})
            self.ready_cache(len(block_tag) + (2 if target_tag_type == 'start' else 3), False)
            self.process_cache(preserve_unclosed_tag)
            return
        
        if preserve_unclosed_tag:
            idx, block_tag = self.search_possible_block_tag(target_tag_type)
            if block_tag is not None:
                self.ready_cache(idx)
                return
        
        if self.cache:
            self.ready_cache(len(self.cache))


class NonBlockingStreamingResponse(StreamingResponse):
    

    def __init__(
            self,
            log_folder: str,
            content: Union[Generator, AsyncGenerator],
            buffer_size: int = 10,
            timeout: float = 0.1,
            **kwargs
    ):
        self.log_folder = log_folder
        self.original_content = content
        self.buffer_size = buffer_size
        self.timeout = timeout

        super().__init__(
            self._wrap_generator(),
            **kwargs
        )

    @staticmethod
    def _is_async_generator(obj: Union[Generator, AsyncGenerator]) -> bool:
        
        return (
                hasattr(obj, '__aiter__') or
                inspect.isasyncgen(obj) or
                inspect.isasyncgenfunction(obj)
        )

    async def _wrap_generator(self) -> AsyncGenerator:
        
        thread_queue = queue.Queue(maxsize=self.buffer_size)
        error_container: list[Optional[Exception]] = [None]

        def worker() -> None:
            
            try:
                if NonBlockingStreamingResponse._is_async_generator(self.original_content):
                    
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        async def async_iter() -> None:
                            async for item in self.original_content:
                                thread_queue.put(('data', item))

                        loop.run_until_complete(async_iter())
                    finally:
                        loop.close()
                else:
                    
                    for item in self.original_content:
                        thread_queue.put(('data', item))

                
                thread_queue.put(('finished', None))

            except Exception as e:
                error_container[0] = e
                thread_queue.put(('error', e))

        
        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        response_manager = ResponseManager(interval=0.5)
        try:
            while True:
                try:
                    
                    msg_type, data = thread_queue.get(timeout=self.timeout)

                    if msg_type == 'data':
                        response_manager.delta(data)
                        while response_manager.ready_contents:
                            yield response_manager.ready_contents.pop(0)
                            await asyncio.sleep(0.1)
                    elif msg_type == 'finished':
                        response_manager.flush()
                        while response_manager.ready_contents:
                            yield response_manager.ready_contents.pop(0)
                            await asyncio.sleep(0.1)
                        break
                    elif msg_type == 'error':
                        raise data

                except queue.Empty:
                    
                    await asyncio.sleep(0)

                    
                    if not thread.is_alive():
                        if error_container[0]:
                            raise error_container[0]
                        
                        try:
                            while True:
                                msg_type, data = thread_queue.get_nowait()
                                if msg_type == 'data':
                                    response_manager.delta(data)
                                    while response_manager.ready_contents:
                                        yield response_manager.ready_contents.pop(0)
                                        await asyncio.sleep(0.1)
                                elif msg_type == 'finished':
                                    response_manager.flush()
                                    while response_manager.ready_contents:
                                        yield response_manager.ready_contents.pop(0)
                                        await asyncio.sleep(0.1)
                                    return
                                elif msg_type == 'error':
                                    raise data
                        except queue.Empty:
                            break

        finally:
            
            save(f'{self.log_folder}/full_response.md', response_manager.full_response)
            save(f'{self.log_folder}/stat.json', response_manager.stat)
            if thread.is_alive():
                thread.join(timeout=1)
