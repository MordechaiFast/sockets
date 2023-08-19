from argparse import ArgumentParser, Namespace
from selectors import DefaultSelector, EVENT_READ , EVENT_WRITE
from socket import AF_INET, SOCK_STREAM
from socket import socket as Socket

from handler_lib import ClientHandler

def parse_args() -> Namespace:
    parser = ArgumentParser()
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--action', default='GET ')
    parser.add_argument('--value', default='/')
    return parser.parse_args()


def main(host: str, port: int, action: str, value: str) -> None:
    selector = DefaultSelector()
    socket = Socket(AF_INET, SOCK_STREAM)
    socket.connect_ex((host, port))
    label = f"{host}:{port}"
    print(f"Starting connection to {label}")
    request = create_request(action, value)
    ClientHandler(selector, socket, label, request).register()
    try:
        while selector.get_map():
            # while there are sockets being monitored
            events = selector.select(timeout=1)
            for key, actions in events:
                handler = key.data
                try:
                    if actions & EVENT_WRITE:
                        handler.write()
                    if actions & EVENT_READ:
                        handler.read()
                except (ValueError, TypeError, ConnectionError) as error:
                    print(f"Error on {handler}:\n{error}")
                    handler.close()
        print("All connections closed. Exiting.")
    except KeyboardInterrupt:
        print("\nKeyboard interrupt received, exiting.")
    finally:
        selector.close()


def create_request(action, value):
    if action == "search":
        return {
            "type": "text/json",
            "encoding": "utf-8",
            "content": {"action": action, "value": value},
        }
    else:
        return {
            "type": "binary/custom-client-binary-type",
            "encoding": "binary",
            "content": (action + value).encode(),
        }


if __name__ == '__main__':
    args = parse_args()
    main(args.host, args.port, args.action, args.value)
