import subprocess
import time


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


class StopPipeline(Exception):
    pass


def format_seconds(seconds):
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes:d}m {secs:02d}s" if minutes else f"{secs:d}s"


class Stages:
    def __init__(self, label, total):
        self.label = label
        self.total = total
        self.rows = []
        self.index = 0
        self.started = time.time()

    def run(self, title, function):
        self.index += 1
        print("")
        print("=" * 78)
        print(f" {self.label} - stage {self.index}/{self.total}: {title}")
        print("=" * 78, flush=True)
        begin = time.time()
        try:
            result = function()
        except StopPipeline as problem:
            self.rows.append((title, time.time() - begin, "STOPPED"))
            print(f"\n STOPPED: {problem}")
            raise
        except Exception:
            self.rows.append((title, time.time() - begin, "CRASHED"))
            print(self.table())
            raise
        elapsed = time.time() - begin
        self.rows.append((title, elapsed, "ok"))
        print(f"\n -> stage {self.index}/{self.total} finished in {format_seconds(elapsed)}", flush=True)
        return result

    def table(self):
        lines = ["", "-" * 78, " TIME TAKEN", "-" * 78]
        for title, seconds, status in self.rows:
            lines.append(f"  {title:<52} {format_seconds(seconds):>9}  {status}")
        lines.append("-" * 78)
        lines.append(f"  {'TOTAL':<52} {format_seconds(time.time() - self.started):>9}")
        lines.append("-" * 78)
        return "\n".join(lines)


def run_live(command, label, capture_prefix=None):
    print(f"   $ {' '.join(str(part) for part in command)}", flush=True)
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1)
    captured = None
    for line in process.stdout:
        text = line.rstrip()
        print("   " + text, flush=True)
        if capture_prefix and text.startswith(capture_prefix):
            captured = text[len(capture_prefix):]
    code = process.wait()
    if code != 0:
        raise StopPipeline(f"{label} failed with exit code {code}")
    return captured
