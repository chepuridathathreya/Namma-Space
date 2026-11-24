import argparse
import functools
import http.server
import os
import socket
import webbrowser


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, format, *args):
        return


def first_free_port(start):
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if probe.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise SystemExit("No free port found near " + str(start))


def lan_address():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        try:
            probe.connect(("10.255.255.255", 1))
            return probe.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main():
    parser = argparse.ArgumentParser(description="Serve this scene website without browser caching")
    parser.add_argument("--port", type=int, default=8764)
    parser.add_argument("--lan", action="store_true", help="also allow phones on the same Wi-Fi")
    parser.add_argument("--no-browser", action="store_true")
    arguments = parser.parse_args()
    folder = os.path.dirname(os.path.abspath(__file__))
    port = first_free_port(arguments.port)
    host = "0.0.0.0" if arguments.lan else "127.0.0.1"
    handler = functools.partial(NoCacheHandler, directory=folder)
    server = http.server.ThreadingHTTPServer((host, port), handler)
    print(f"Open on this computer : http://localhost:{port}/index.html")
    if arguments.lan:
        print(f"Open on your phone    : http://{lan_address()}:{port}/index.html")
    print("Stop with Ctrl+C", flush=True)
    if not arguments.no_browser:
        webbrowser.open(f"http://localhost:{port}/index.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
