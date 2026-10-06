export function MinimalDashboard() {
  return (
    <div style={{ 
      backgroundColor: '#1f2937', 
      color: 'white', 
      padding: '20px',
      minHeight: '100vh'
    }}>
      <h1 style={{ fontSize: '24px', marginBottom: '20px' }}>
        JARVIS Dashboard - Test
      </h1>
      <div style={{ backgroundColor: '#374151', padding: '15px', borderRadius: '8px' }}>
        <p>Dashboard is working!</p>
        <p>Time: {new Date().toLocaleTimeString()}</p>
      </div>
    </div>
  );
}
