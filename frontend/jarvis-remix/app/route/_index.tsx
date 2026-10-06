export default function IndexRoute() {
  return (
    <div style={{ 
      backgroundColor: '#1f2937', 
      color: 'white', 
      padding: '20px',
      minHeight: '100vh',
      fontFamily: 'Arial, sans-serif'
    }}>
      <h1 style={{ fontSize: '32px', marginBottom: '20px' }}>
        JARVIS - Test Page
      </h1>
      <p style={{ fontSize: '18px', marginBottom: '10px' }}>
        Server is working correctly!
      </p>
      <p style={{ fontSize: '16px', color: '#9ca3af' }}>
        Time: {new Date().toLocaleTimeString()}
      </p>
      <div style={{ 
        backgroundColor: '#374151', 
        padding: '20px', 
        borderRadius: '8px',
        marginTop: '20px'
      }}>
        <p>If you can see this page, the Remix server is working.</p>
        <p>Click <a href="/dashboard" style={{ color: '#3b82f6' }}>here</a> to go to dashboard.</p>
      </div>
    </div>
  );
}
