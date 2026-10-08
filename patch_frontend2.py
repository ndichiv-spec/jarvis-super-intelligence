path = r'F:\AI\Jarvis-super-intelligence-\frontend/web/src/components/real-ai-chat.tsx'
with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

old_crlf = (
    'setUsingLocalFallback(!data.enabled);\r\n'
    '    } catch (error) {\r\n'
    '      console.error("Failed to load system status:", error);\r\n'
    '      setBackendConnected(false);\r\n'
    '      setUsingLocalFallback(true);\r\n'
    '    }'
)
new_crlf = (
    'setUsingLocalFallback(!data.enabled);\r\n'
    '      // When the platform is degraded (no real provider can execute),\r\n'
    '      // reflect this in the UI so the user knows replies may not be real.\r\n'
    '      if (data.status === "degraded" && !data.enabled) {\r\n'
    '        setUsingLocalFallback(true);\r\n'
    '      }\r\n'
    '    } catch (error) {\r\n'
    '      console.error("Failed to load system status:", error);\r\n'
    '      setBackendConnected(false);\r\n'
    '      setUsingLocalFallback(true);\r\n'
    '    }'
)

if old_crlf in content:
    content = content.replace(old_crlf, new_crlf)
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(content)
    print('FIX applied (CRLF): loadSystemStatus handles degraded status')
else:
    old_lf = old_crlf.replace('\r\n', '\n')
    new_lf = new_crlf.replace('\r\n', '\n')
    if old_lf in content:
        content = content.replace(old_lf, new_lf)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        print('FIX applied (LF): loadSystemStatus handles degraded status')
    else:
        print('FAIL: pattern not found')
        idx = content.find('setUsingLocalFallback(!data.enabled)')
        if idx >= 0:
            print(repr(content[idx-10:idx+300]))
