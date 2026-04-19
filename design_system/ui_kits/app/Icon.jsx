// Icon — a small SVG lookup keyed by name (Lucide 1.5)
function Icon({ name, size=16, color }) {
  const stroke = color || 'currentColor';
  const props = {width:size,height:size,viewBox:'0 0 24 24',fill:'none',stroke,strokeWidth:1.5,strokeLinecap:'round',strokeLinejoin:'round'};
  switch(name){
    case 'search': return (<svg {...props}><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>);
    case 'book':   return (<svg {...props}><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>);
    case 'db':     return (<svg {...props}><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14a9 3 0 0 0 18 0V5"/><path d="M3 12a9 3 0 0 0 18 0"/></svg>);
    case 'table':  return (<svg {...props}><path d="M3 3h18v18H3z"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/></svg>);
    case 'col':    return (<svg {...props}><path d="M3 3h18v18H3z"/><path d="M9 3v18M15 3v18"/></svg>);
    case 'check':  return (<svg {...props}><path d="M20 6 9 17l-5-5"/></svg>);
    case 'clock':  return (<svg {...props}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>);
    case 'user':   return (<svg {...props}><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>);
    case 'arrow':  return (<svg {...props}><path d="M5 12h14M13 5l7 7-7 7"/></svg>);
    case 'chev':   return (<svg {...props}><path d="m9 6 6 6-6 6"/></svg>);
    case 'filter': return (<svg {...props}><path d="M3 4h18l-7 9v5l-4 2v-7z"/></svg>);
    case 'tag':    return (<svg {...props}><path d="M20 12 12 20 3 11V3h8z"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor"/></svg>);
    case 'lock':   return (<svg {...props}><rect x="4" y="11" width="16" height="10" rx="1"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>);
    case 'link':   return (<svg {...props}><path d="M10 14a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"/><path d="M14 10a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"/></svg>);
    case 'copy':   return (<svg {...props}><rect x="9" y="9" width="12" height="12" rx="1"/><path d="M5 15V5a1 1 0 0 1 1-1h10"/></svg>);
    default: return null;
  }
}
window.Icon = Icon;
