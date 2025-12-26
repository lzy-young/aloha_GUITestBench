import os
import signal

from PyQt5.QtWidgets import QApplication, QWidget
from PyQt5.QtCore import QTimer
import multiprocessing
import threading
import sys
from pynput import keyboard as kb



class MyWidget(QWidget):
    def __init__(self, request_queue, response_queue):
        super().__init__()
        self._request_queue = request_queue
        self._response_queue = response_queue

        
        self.__data_listener_timer = QTimer()
        self.__data_listener_timer.timeout.connect(self.process_requests)
        self.__data_listener_timer.start(100)

    def process_requests(self):
        
        while not self._request_queue.empty():
            data = self._request_queue.get()
            self._receive(data)

    def _receive(self, data: str):
        
        raise NotImplementedError

    def _send(self, data: str):
        
        self._response_queue.put(data)

    def run(self):
        
        self.show()
        QApplication.instance().exec_()

    def closeEvent(self, event):
        self._request_queue.put('EXIT')
        event.accept()



class AppContext:
    

    def __init__(self, widget_cls, args=None, kwargs=None):
        self.request_queue = multiprocessing.Queue()
        self.response_queue = multiprocessing.Queue()
        self.args = args or []
        self.kwargs = kwargs or {}

        self.process = multiprocessing.Process(
            target=AppContext.start_gui,
            args=(widget_cls, self.request_queue, self.response_queue, *args),
            kwargs=self.kwargs
        )
        self.process.start()

        self.callback = None  
        self.running = True

        
        self.kill_listener = kb.GlobalHotKeys({'<ctrl>+<shift>+q': self.force_quit})
        self.kill_listener.start()
        self.listener_thread = threading.Thread(target=self.__listen_for_responses, daemon=True)
        self.listener_thread.start()

    def set_callback(self, callback):
        
        self.callback = callback

    def send(self, data: str):
        
        self.request_queue.put(data)

    def __listen_for_responses(self):

        while self.running:
            try:
                data = self.response_queue.get(timeout=1)
                if data == 'EXIT':
                    self.running = False
                    self.process.terminate()
                    self.process.join()
                    return
                if self.callback:
                    self.callback(data)
            except Exception:
                pass  

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        
        self.running = False
        self.process.terminate()
        self.process.join()

    @staticmethod
    def start_gui(widget_cls, request_queue, response_queue, *args, **kwargs):
        
        if QApplication.instance() is None:
            
            _ = QApplication(sys.argv)
        widget = widget_cls(*args, request_queue, response_queue, **kwargs)
        widget.run()

    def force_quit(self):
        if self.process and self.process.is_alive():
            print("Force quitting MyApp process...")
            os.kill(self.process.pid, signal.SIGTERM) 
            self.process.terminate()
            self.process.close()
            print("MyApp process terminated.")
            sys.exit()


