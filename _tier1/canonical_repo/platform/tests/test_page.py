import urllib.request


def run_page_smoke():
    try:
        with urllib.request.urlopen("http://localhost:5000/", timeout=3) as response:
            content = response.read().decode()
        print(f"Page size: {len(content)} bytes")
        print(f'Has chat panel: {"chat-panel" in content}')
        print('Has files panel:', 'id="files"' in content)
        print('Has processes:', 'id="processes"' in content)
        print('Has knowledge:', 'id="knowledge"' in content)
    except OSError as exc:
        print(f"Page smoke check unavailable: {exc}")


if __name__ == "__main__":
    run_page_smoke()
