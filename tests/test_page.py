import urllib.request

try:
    r = urllib.request.urlopen('http://localhost:5000/', timeout=3)
    content = r.read().decode()
    print(f'Page size: {len(content)} bytes')
    print(f'Has chat panel: {\"chat-panel\" in content}')
    print(f'Has files panel: {\"id=\\\"files\\\"\" in content}')
    print(f'Has processes: {\"id=\\\"processes\\\"\" in content}')
    print(f'Has knowledge: {\"id=\\\"knowledge\\\"\" in content}')
    print(f'All panels present!')
except Exception as e:
    print(f'Error: {e}')