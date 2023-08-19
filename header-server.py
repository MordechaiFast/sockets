from argparse import ArgumentParser, Namespace
from selectors import BaseSelector, DefaultSelector, EVENT_READ, EVENT_WRITE
from socket import AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from socket import socket as Socket

from handler_lib import ServerHandler


def parse_args() -> Namespace:
    parser = ArgumentParser()
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=8000)
    return parser.parse_args()


def main(host: str, port: int) -> None:
    selector = DefaultSelector()
    listening_socket = Socket(AF_INET, SOCK_STREAM)
    # Avoid bind() exception: OSError: [Errno 48] Address already in use
    listening_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
    listening_socket.bind((host, port))
    listening_socket.listen()
    listening_socket.setblocking(False)
    print(f"Listening on to {host}:{port}")
    selector.register(listening_socket, EVENT_READ, data=None)
    try:
        while True:
            # while there are sockets being monitored
            events = selector.select(timeout=None)
            for key, actions in events:
                handler = key.data
                try:
                    if handler is None:
                        accept_wrapper(selector, key.fileobj)
                    else:
                        if actions & EVENT_READ:
                            handler.read()
                        if actions & EVENT_WRITE:
                            handler.write()
                except (ValueError, TypeError, ConnectionError) as error:
                    print(f"Error on {handler}:\n{error}")
                    handler.close()
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting.")
    finally:
        selector.close()


def accept_wrapper(selector: BaseSelector, socket: Socket) -> None:
    connection, addr = socket.accept()
    label = f"{addr[0]}:{addr[1]}"
    print(f"Accepting connection from {label}")
    ServerHandler(selector, connection, label).register()


if __name__ == '__main__':
    args = parse_args()
    main(args.host, args.port)
