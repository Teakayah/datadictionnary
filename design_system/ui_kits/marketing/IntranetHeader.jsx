// IntranetHeader — internal-only top bar, no CTAs
function IntranetHeader() {
  return (
    <header style={{borderBottom:'1px solid var(--ink-20)', background:'rgba(250,247,240,.92)', backdropFilter:'blur(8px)', position:'sticky', top:0, zIndex:10}}>
      <div style={{maxWidth:1200, margin:'0 auto', padding:'16px 48px', display:'flex', alignItems:'center', gap:24}}>
        <a href="#" style={{display:'flex',alignItems:'center',gap:12,textDecoration:'none'}}>
          <img src="../../assets/logo-mark.svg" alt="" style={{height:30}}/>
          <span style={{fontFamily:'var(--font-display)', fontSize:22, fontWeight:500, color:'var(--ink)', letterSpacing:'-.01em'}}>Data Dictionary</span>
          <span style={{marginLeft:6,fontSize:10,padding:'2px 8px',border:'1px solid var(--ink)',borderRadius:999,letterSpacing:'.1em',textTransform:'uppercase',fontWeight:600}}>Internal</span>
        </a>
        <nav style={{marginLeft:'auto',display:'flex',gap:28,alignItems:'center'}}>
          <a href="#about" style={{fontSize:14}}>About</a>
          <a href="#architecture" style={{fontSize:14}}>Architecture</a>
          <a href="#docs" style={{fontSize:14}}>Docs</a>
          <a href="#support" style={{fontSize:14}}>Support</a>
          <span className="meta" style={{fontSize:12,fontFamily:'var(--font-mono)'}}>§ data-platform</span>
        </nav>
      </div>
    </header>
  );
}
window.IntranetHeader = IntranetHeader;
