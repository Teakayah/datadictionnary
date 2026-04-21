// AppShell — outer frame: sticky header + main column
function AppShell({ children, user, onLogout }) {
  return (
    <div style={{
      minHeight:'100vh', 
      background:'var(--paper-deep)', 
      display:'flex', 
      justifyContent:'center', 
      padding:'20px 0'
    }}>
      <div style={{
        width:'95%',
        maxWidth:'1280px',
        background:'var(--paper)',
        boxShadow:'0 32px 64px -16px rgba(20,17,12,0.12)',
        borderRadius:8,
        display:'flex',
        flexDirection:'column',
        minHeight:'calc(100vh - 40px)',
        overflow:'hidden'
      }}>
        <header style={{
          position:'sticky', top:0, zIndex:10,
          background:'rgba(250,247,240,.92)', backdropFilter:'blur(8px)',
          borderBottom:'1px solid var(--ink-20)'
        }}>
          <div style={{maxWidth:1200, margin:'0 auto', padding:'14px 48px', display:'flex', alignItems:'center', gap:24}}>
          <a href="#" style={{display:'flex',alignItems:'center',gap:12,textDecoration:'none'}}>
            <img src="../../assets/logo-mark.svg" alt="" style={{height:30}}/>
            <span style={{fontFamily:'var(--font-display)', fontSize:22, fontWeight:500, color:'var(--ink)', letterSpacing:'-.01em'}}>Data Dictionary</span>
            <span className="pill" style={{marginLeft:6,fontSize:10,padding:'2px 8px',border:'1px solid var(--ink)',borderRadius:999,letterSpacing:'.1em',textTransform:'uppercase',fontWeight:600}}>Beta</span>
          </a>
          <nav style={{marginLeft:'auto',display:'flex',gap:22,alignItems:'center'}}>
            <a href="#" style={{fontSize:14}}>Catalog</a>
            <a href="#" style={{fontSize:14}}>Glossary</a>
            <a href="#" style={{fontSize:14}}>Lineage</a>
            <span style={{width:1,height:20,background:'var(--ink-20)'}}/>
            {user ? (
              <>
                <span className="meta" style={{fontSize:12}}>{user}</span>
                <button onClick={onLogout} className="btn ghost">Sign out</button>
              </>
            ) : null}
          </nav>
        </div>
      </header>
      <main style={{maxWidth:1200, margin:'0 auto', padding:'48px'}}>{children}</main>
      <footer style={{borderTop:'1px solid var(--ink-10)', marginTop:96, padding:'32px 48px'}}>
        <div style={{maxWidth:1200, margin:'0 auto', display:'flex', justifyContent:'space-between', fontSize:12, color:'var(--ink-40)', fontFamily:'var(--font-mono)'}}>
          <span>Data Dictionary · v0.3.0 · synced 04:12 UTC</span>
          <span>main.data_governance.dictionary_cache</span>
        </div>
      </footer>
      </div>
    </div>
  );
}
window.AppShell = AppShell;
