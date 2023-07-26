import io
import json
import selectors
import struct
import sys
from socket import socket as Socket


class SocketHandler:
    def __init__(self, socket, addr) -> None:
        self.socket: Socket = socket
        self.addr: tuple = addr
        self._out_buffer: bytes = b""
        self.finished_writing: bool = True
        self.received: bytes = b""

    def buffer(self, message: bytes):
        self._out_buffer += message
        self.finished_writing = False

    def write(self):
        if not self.finished_writing:
            print(f"Sending {self._out_buffer!r} to {self.addr}")
            try:
                sent = self.socket.send(self._out_buffer)
                self._out_buffer = self._out_buffer[sent:]
            except BlockingIOError:
                # Resource temporarily unavailable (errno EWOULDBLOCK)
                pass
            if not self._out_buffer:
                self.finished_writing = True

    def read(self):
        try:
            if (data := self.socket.recv(4096)):
                self.received += data
            else:
                raise ConnectionError("Peer closed.")
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
    
    def close(self):
        print(f"Closing connection to {self.addr}")
        try:
            self.socket.close()
        except OSError as error:
            print(f"Error: socket.close() exception for {self.addr}: {error!r}")
        finally:
            # Delete reference to socket object for garbage collection
            self.socket = None


def json_encode(self, obj, encoding):
        return json.dumps(obj, ensure_ascii=False).encode(encoding)
    
def json_decode(json_bytes, encoding):
    wrapper = io.TextIOWrapper(
        io.BytesIO(json_bytes), encoding=encoding, newline=""
    )
    decoded_jason = json.load(wrapper)
    wrapper.close()
    return decoded_jason
        
class MessageHandler(SocketHandler):
    def __init__(self, socket, addr) -> None:
        super().__init__(socket, addr)
        self._json_header_len: int = None
        self.json_header: dict = None
        self.content: bytes = None

    def create_message(self, content_bytes, content_type, content_encoding):
        json_header = {
            "byteorder": sys.byteorder,
            "content-type": content_type,
            "content-encoding": content_encoding,
            "content-length": len(content_bytes),
        }
        json_header_bytes = json_encode(json_header, "utf-8")
        message_header = struct.pack(">H", len(json_header_bytes))
        message = message_header + json_header_bytes + content_bytes
        self.buffer(message)    
    
    def read(self):
        super().read()
        if self._json_header_len is None:
            self._process_protoheader()
        if self._json_header_len:
            if self.json_header is None:
                self._process_json_header()
            if self.json_header:
                if self.content is None:
                    self._process_content()
                if self.content:
                    self.decode_content()

    def _process_protoheader(self):
        header_length = 2
        if len(self.received) >= header_length:
            self._json_header_len = struct.unpack(
                ">H", self.received[:header_length]
            )[0]
            self.received = self.received[header_length:]

    def _process_json_header(self):
        header_length = self._json_header_len
        if len(self.received) >= header_length:
            self.json_header = json_decode(
                self.received[:header_length], "utf-8"
            )
            self.received = self.received[header_length:]
            for required_header in (
                "byteorder",
                "content-length",
                "content-type",
                "content-encoding",
            ):
                if required_header not in self.json_header:
                    raise ValueError(
                        f"Missing required header '{required_header}'.")

    def _process_content(self):
        content_len = self.json_header["content-length"]
        if len(self.received) >= content_len:
            self.content = self.received[:content_len]
            self.received = self.received[content_len:]

    def decode_content(self):
        if self.json_header["content-type"] == "text/json":
            encoding = self.json_header["content-encoding"]
            self.content = json_decode(self.content, encoding)
            print(f"Received {self.content!r} from {self.addr}")
        else:
            # Binary or unknown content-type
            print(
                f"Received {self.json_header['content-type']} from {self.addr}"
            )
        

class ClientHandler(MessageHandler):
    def __init__(self, selector, socket, addr, request):
        super().__init__(socket, addr)
        self.selector: selectors.BaseSelector = selector
        self.request: dict = request
        self._request_queued: bool = False
   
    def queue_request(self):
        content = self.request["content"]
        content_type = self.request["type"]
        content_encoding = self.request["encoding"]
        if content_type == "text/json":
            content_bytes = json_encode(content, content_encoding)
        else:
            content_bytes = content
        self.create_message(
            content_bytes, content_type, content_encoding)
        self._request_queued = True

    def write(self):
        if not self._request_queued:
            self.queue_request()
        super().write()
        if self.finished_writing:
            self.selector.modify(self.socket, selectors.EVENT_READ, data=self)

    def read(self):
        super().read()
        if self.content:
            # the full message has been read
            if self.json_header["content-type"] == "text/json":
                self._act_upon_json()
            else:
                self._act_upon_binary()
            self.close()
    
    def _act_upon_json(self):
        print(f"Got result: {self.content.get('result')}")

    def _act_upon_binary(self):
        print(f"Got response: {self.content!r}")

    def close(self):
        try:
            self.selector.unregister(self.socket)
        except Exception as error:
            print(
                f"Error: selector.unregister() exception for "
                f"{self.addr}: {error!r}"
            )
        finally:
            super().close()


request_search = {
    "morpheus": "Follow the white rabbit. \U0001f430",
    "ring": "In the caves beneath the Misty Mountains. \U0001f48d",
    "\U0001f436": "\U0001f43e Playing ball! \U0001f3d0",
}

class ServerHandler(MessageHandler):
    def __init__(self, selector, socket, addr) -> None:
        super().__init__(socket, addr)
        self.selector: selectors.BaseSelector = selector
        self._response_created: bool = False

    def read(self):
        super().read()
        if self.content:
            # the full message has been read
            self.selector.modify(self.socket, selectors.EVENT_WRITE, data=self)

    def write(self):
        if self.content:
            # the full message has been read
            if not self._response_created:
                self.create_response()
        super().write()
        if self._response_created:
            if self.finished_writing:
                self.close()

    def create_response(self):
        if self.json_header["content-type"] == "text/json":
            response = self._create_response_json_content()
        else:
            # Binary or unknown content-type
            response = self._create_response_binary_content()
        self.create_message(**response)
        self._response_created = True

    def _create_response_json_content(self):
        action = self.content.get("action")
        if action == "search":
            query = self.content.get("value")
            answer = request_search.get(query) or f"No match for '{query}'."
            content = {"result": answer}
        else:
            content = {"result": f"Error: invalid action '{action}'."}
        content_encoding = "utf-8"
        response = {
            "content_bytes": json_encode(content, content_encoding),
            "content_type": "text/json",
            "content_encoding": content_encoding,
        }
        return response

    def _create_response_binary_content(self):
        response = {
            "content_bytes": b"First 10 bytes of request: "
            + self.content[:10],
            "content_type": "binary/custom-server-binary-type",
            "content_encoding": "binary",
        }
        return response
    
    def close(self):
        try:
            self.selector.unregister(self.socket)
        except Exception as error:
            print(
                f"Error: selector.unregister() exception for "
                f"{self.addr}: {error!r}"
            )
        finally:
            super().close()
