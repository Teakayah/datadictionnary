// InternalFooter — bare-bones internal links
function InternalFooter() {
  return (
    <footer style={{padding:'32px 48px',borderTop:'1px solid var(--ink-10)',background:'var(--paper)'}}>
      <div style={{maxWidth:1040,margin:'0 auto',display:'flex',justifyContent:'space-between',alignItems:'center',flexWrap:'wrap',gap:16}}>
        <div style={{display:'flex',gap:20,fontSize:13}}>
          <a href="#">Docs</a>
          <a href="#">#data-platform</a>
          <a href="#">Data access policy</a>
          <a href="#">Support</a>
        </div>
        <div style={{fontFamily:'var(--font-mono)',fontSize:11,color:'var(--ink-40)'}}>
          Internal use only · data platform team · v0.3.0
        </div>
      </div>
    </footer>
  );
}
window.InternalFooter = InternalFooter;
