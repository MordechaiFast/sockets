import sys
import selectors
from socket import socket as Socket
import json
import io
import struct


class MessageHandler:
    def __init__(self, selector, socket, addr) -> None:
        self.selector: selectors.BaseSelector = selector
        self.socket: Socket = socket
        self.addr: tuple = addr
        self._in_buffer: bytes = b""
        self._out_buffer: bytes = b""
        self._json_header_len: int = None
        self.json_header: dict = None

    def _write(self):
        if self._out_buffer:
            print(f"Sending {self._out_buffer!r} to {self.addr}")
            try:
                sent = self.socket.send(self._out_buffer)
                self._out_buffer = self._out_buffer[sent:]
            except BlockingIOError:
                # Resource temporarily unavailable (errno EWOULDBLOCK)
                pass

    def _set_selector_events_mask(self, mode):
        """Set selector to listen for events: mode is 'r', 'w', or 'rw'."""
        if mode == "r":
            events = selectors.EVENT_READ
        elif mode == "w":
            events = selectors.EVENT_WRITE
        elif mode == "rw":
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
        else:
            raise ValueError(f"Invalid events mask mode {mode!r}.")
        self.selector.modify(self.socket, events, data=self)

    def _read(self):
        try:
            if (data := self.socket.recv(4096)):
                self._in_buffer += data
            else:
                raise ConnectionError("Peer closed.")
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass
        if self._json_header_len is None:
            self.process_protoheader()
        if self._json_header_len is not None:
            if self.json_header is None:
                self.process_jsonheader()
        
    def _json_encode(self, obj, encoding):
        return json.dumps(obj, ensure_ascii=False).encode(encoding)

    def _json_decode(self, json_bytes, encoding):
        wrapper = io.TextIOWrapper(
            io.BytesIO(json_bytes), encoding=encoding, newline=""
        )
        decoded_jason = json.load(wrapper)
        wrapper.close()
        return decoded_jason

    def process_protoheader(self):
        header_length = 2
        if len(self._in_buffer) >= header_length:
            self._json_header_len = struct.unpack(
                ">H", self._in_buffer[:header_length]
            )[0]
            self._in_buffer = self._in_buffer[header_length:]

    def process_jsonheader(self):
        header_length = self._json_header_len
        if len(self._in_buffer) >= header_length:
            self.json_header = self._json_decode(
                self._in_buffer[:header_length], "utf-8"
            )
            self._in_buffer = self._in_buffer[header_length:]
            for required_header in (
                "byteorder",
                "content-length",
                "content-type",
                "content-encoding",
            ):
                if required_header not in self.json_header:
                    raise ValueError(
                        f"Missing required header '{required_header}'.")

    def _create_message(self, content_bytes, content_type, content_encoding):
        json_header = {
            "byteorder": sys.byteorder,
            "content-type": content_type,
            "content-encoding": content_encoding,
            "content-length": len(content_bytes),
        }
        json_header_bytes = self._json_encode(json_header, "utf-8")
        message_header = struct.pack(">H", len(json_header_bytes))
        message = message_header + json_header_bytes + content_bytes
        return message
    
    def close(self):
        print(f"Closing connection to {self.addr}")
        try:
            self.selector.unregister(self.socket)
        except Exception as error:
            print(
                f"Error: selector.unregister() exception for "
                f"{self.addr}: {error!r}"
            )

        try:
            self.socket.close()
        except OSError as error:
            print(f"Error: socket.close() exception for {self.addr}: {error!r}")
        finally:
            # Delete reference to socket object for garbage collection
            self.socket = None


class ClientMessage(MessageHandler):
    def __init__(self, selector, socket, addr, request):
        super.__init__(selector, socket, addr)
        self._request_queued: bool = False
        self.request: dict = request
        self.response: bytes = None

    def write(self):
        if not self._request_queued:
            self.queue_request()
        self._write()
        if not self._out_buffer:
            # Set selector to listen for read events, we're done writing.
            self._set_selector_events_mask("r")

    def queue_request(self):
        content = self.request["content"]
        content_type = self.request["type"]
        content_encoding = self.request["encoding"]
        if content_type == "text/json":
            content_bytes = self._json_encode(content, content_encoding)
        else:
            content_bytes = content
        message = self._create_message(
            content_bytes, content_type, content_encoding)
        self._out_buffer += message
        self._request_queued = True
        
    def read(self):
        self._read()
        if self.json_header:
            if self.response is None:
                self.process_response()

    def process_response(self):
        content_len = self.json_header["content-length"]
        if not len(self._in_buffer) >= content_len:
            return
        data = self._in_buffer[:content_len]
        self._in_buffer = self._in_buffer[content_len:]
        if self.json_header["content-type"] == "text/json":
            encoding = self.json_header["content-encoding"]
            self.response = self._json_decode(data, encoding)
            print(f"Received response {self.response!r} from {self.addr}")
            self._process_response_json_content()
        else:
            # Binary or unknown content-type
            self.response = data
            print(
                f"Received {self.json_header['content-type']} "
                f"response from {self.addr}"
            )
            self._process_response_binary_content()
        # Close when response has been processed
        self.close()

    def _process_response_json_content(self):
        content = self.response
        result = content.get("result")
        print(f"Got result: {result}")

    def _process_response_binary_content(self):
        content = self.response
        print(f"Got response: {content!r}")

request_search = {
    "morpheus": "Follow the white rabbit. \U0001f430",
    "ring": "In the caves beneath the Misty Mountains. \U0001f48d",
    "\U0001f436": "\U0001f43e Playing ball! \U0001f3d0",
}

class ServerMessage(MessageHandler):
    def __init__(self, selector, socket, addr) -> None:
        super().__init__(selector, socket, addr)
        self.request = None
        self.response_created: bool = False

    def read(self):
        self._read()
        if self.jsonheader:
            if self.request is None:
                self.process_request()

    def process_request(self):
        content_len = self.jsonheader["content-length"]
        if not len(self._in_buffer) >= content_len:
            return
        data = self._in_buffer[:content_len]
        self._in_buffer = self._in_buffer[content_len:]
        if self.jsonheader["content-type"] == "text/json":
            encoding = self.jsonheader["content-encoding"]
            self.request = self._json_decode(data, encoding)
            print(f"Received request {self.request!r} from {self.addr}")
        else:
            # Binary or unknown content-type
            self.request = data
            print(
                f"Received {self.jsonheader['content-type']} "
                f"request from {self.addr}"
            )
        # Set selector to listen for write events, we're done reading.
        self._set_selector_events_mask("w")

    def write(self):
        if self.request:
            if not self.response_created:
                self.create_response()
        self._write()
        # Close when the buffer is drained. The response has been sent.
        if self.response_created and not self._out_buffer:
            self.close()

    def create_response(self):
        if self.jsonheader["content-type"] == "text/json":
            response = self._create_response_json_content()
        else:
            # Binary or unknown content-type
            response = self._create_response_binary_content()
        message = self._create_message(**response)
        self.response_created = True
        self._out_buffer += message

    def _create_response_json_content(self):
        action = self.request.get("action")
        if action == "search":
            query = self.request.get("value")
            answer = request_search.get(query) or f"No match for '{query}'."
            content = {"result": answer}
        else:
            content = {"result": f"Error: invalid action '{action}'."}
        content_encoding = "utf-8"
        response = {
            "content_bytes": self._json_encode(content, content_encoding),
            "content_type": "text/json",
            "content_encoding": content_encoding,
        }
        return response

    def _create_response_binary_content(self):
        response = {
            "content_bytes": b"First 10 bytes of request: "
            + self.request[:10],
            "content_type": "binary/custom-server-binary-type",
            "content_encoding": "binary",
        }
        return response
