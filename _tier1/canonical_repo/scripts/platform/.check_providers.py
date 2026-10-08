import os

# Load .env
with open('.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#'):
            idx = line.find('=')
            if idx > 0:
                k = line[:idx]
                v = line[idx+1:]
                if v:
                    os.environ[k] = v

providers = {
    'openai': ('OPENAI_API_KEY', 'https://api.openai.com/v1'),
    'google': ('GOOGLE_API_KEY', 'https://generativelanguage.googleapis.com/v1beta/openai'),
    'deepseek': ('DEEPSEEK_API_KEY', 'https://api.deepseek.com/v1'),
}

for name, (key, endpoint) in providers.items():
    val = os.environ.get(key, '')
    print(f'{name}: key={"set" if val else "UNSET"}, endpoint={endpoint}')
