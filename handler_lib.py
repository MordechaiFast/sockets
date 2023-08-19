import io
import json
import selectors
import struct
import sys
from socket import socket as Socket


class SocketHandler:
    def __init__(self, socket: Socket, label: str) -> None:
        self.socket: Socket = socket
        self.label = label
        self._out_buffer: bytes = b""
        self.finished_writing: bool = True
        self.received: bytes = b""

    def __str__(self):
        return self.label
        
    def buffer(self, message: bytes):
        self._out_buffer += message
        self.finished_writing = False

    def write(self):
        if not self.finished_writing:
            print(f"Sending {self._out_buffer!r} to {self}")
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
                raise ConnectionAbortedError("Peer closed.")
        except BlockingIOError:
            # Resource temporarily unavailable (errno EWOULDBLOCK)
            pass

    def close(self):
        print(f"Closing connection to {self}")
        try:
            self.socket.close()
        except OSError as error:
            print(
                f"Error: socket.close() exception for {self}: {error!r}")
        finally:
            # Delete reference to socket object for garbage collection
            self.socket = None


class SocketSelector(SocketHandler):
    def __init__(self, selector, socket, label) -> None:
        SocketHandler.__init__(self, socket, label)
        self.selector: selectors.BaseSelector = selector
        
    def register(self):
        try:
            self.selector.register(
                self.socket,
                events=selectors.EVENT_READ | selectors.EVENT_WRITE,
                data=self)
        except Exception as error:
            print(
                f"Error: selector.register() exception for {self}: {error!r}"
            )

        self.socket.setblocking(False)

    def set_selector_events_mask(self, mode: str):
        """Set selector to listen for events.

        mode can be 'r', 'w', or 'rw'.
        """
        if mode == "r":
            events = selectors.EVENT_READ
        elif mode == "w":
            events = selectors.EVENT_WRITE
        elif mode == "rw":
            events = selectors.EVENT_READ | selectors.EVENT_WRITE
        else:
            raise ValueError(f"Invalid events mask mode {mode!r}.")
        self.selector.modify(self.socket, events, data=self)

    def close(self):
        try:
            self.selector.unregister(self.socket)
        except Exception as error:
            print(
                f"Error: selector.unregister() exception for {self}: {error!r}"
            )
        finally:
            super().close()


def json_encode(obj, encoding: str) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode(encoding)

def json_decode(json_bytes: bytes, encoding: str) -> dict:
    wrapper = io.TextIOWrapper(
        io.BytesIO(json_bytes), encoding=encoding, newline=""
    )
    decoded_jason = json.load(wrapper)
    wrapper.close()
    return decoded_jason

class MessageHandler(SocketHandler):
    def __init__(self, socket, label) -> None:
        SocketHandler.__init__(self, socket, label)
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
            print(f"Received {self.content!r} from {self}")
        else:
            # Binary or unknown content-type
            print(
                f"Received {self.json_header['content-type']} from {self}"
            )


class ClientHandler(MessageHandler, SocketSelector):
    def __init__(self, selector, socket, label, request):
        MessageHandler.__init__(self, socket, label)
        SocketSelector.__init__(self, selector, socket, label)
        self.request: dict = request
        self._request_queued: bool = False

    def register(self):
        self.selector.register(
            self.socket,
            events=selectors.EVENT_WRITE,
            data=self)
        self.socket.setblocking(False)

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
            self.set_selector_events_mask("r")

    def read(self):
        super().read()
        if self.content:
            # the full message has been read
            if self.json_header["content-type"] == "text/json":
                self._process_response_json_content()
            else:
                self._process_response_binary_content()
            self.close()

    def _process_response_json_content(self):
        content = self.content
        result = content.get("result")
        print(f"Got result: {result}")

    def _process_response_binary_content(self):
        content = self.content
        print(f"Got response: {content!r}")


request_search = {
    "morpheus": "Follow the white rabbit. \U0001f430",
    "ring": "In the caves beneath the Misty Mountains. \U0001f48d",
    "\U0001f436": "\U0001f43e Playing ball! \U0001f3d0",
}


class ServerHandler(MessageHandler, SocketSelector):
    def __init__(self, selector, socket, label) -> None:
        MessageHandler.__init__(self, socket, label)
        SocketSelector.__init__(self, selector, socket, label)
        self._response_created: bool = False

    def register(self):
        self.selector.register(
            self.socket,
            events=selectors.EVENT_READ,
            data=self)
        self.socket.setblocking(False)

    def read(self):
        super().read()
        if self.content:
            # the full message has been read
            self.set_selector_events_mask("w")

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

    def write(self):
        if self.content:
            # the full message has been read
            if not self._response_created:
                self.create_response()
        super().write()
        if self._response_created:
            if self.finished_writing:
                self.close()
