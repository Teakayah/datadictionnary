// SearchBar — prominent search field
function SearchBar({ value, onChange, onSubmit }) {
  return (
    <form onSubmit={(e)=>{e.preventDefault();onSubmit&&onSubmit(value);}}
      style={{display:'flex',alignItems:'center',gap:12,border:'1px solid var(--ink)',background:'var(--paper)',padding:'14px 16px',borderRadius:2}}>
      <Icon name="search" size={18} />
      <input value={value} onChange={e=>onChange(e.target.value)}
        placeholder="e.g. customer_lifetime_value"
        style={{border:0,outline:0,flex:1,background:'transparent',fontSize:16,fontFamily:'var(--font-sans)',color:'var(--ink)'}} />
      <span className="meta" style={{fontSize:11,fontFamily:'var(--font-mono)'}}>⌘K</span>
      <button type="submit" className="btn" style={{padding:'8px 14px',fontSize:13}}>Search</button>
    </form>
  );
}
window.SearchBar = SearchBar;
